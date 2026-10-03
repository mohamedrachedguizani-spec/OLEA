import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pdfplumber

from .controle import construire_controle, exiger_type
from .models import BalanceAgeeResponse, ClientBalance, LigneTransaction

EPS = 0.0005          # tolérance d'arrondi (1/2 millime)
SEUIL_SOLDE = 0.1     # soldes plus petits ignorés (résidus d'arrondi, ex. 0,053)

# ───────────────────────── Patterns ─────────────────────────
# Le nom peut être collé au code de fin : "PREVENTION DES RISQUES CTN-000036"
# En-tête client : Sage superpose parfois le nom tronqué et le code de fin
# ("FEDERATION NATIONALE DETSN-000019") -> on ne dépend pas de la forme exacte du suffixe.
PAT_CLIENT = re.compile(r"^(TN-\d{6})\s+(.+)$")
PAT_SUFFIXE_EXACT = re.compile(r"\s*TN-\d{6}$")
PAT_SUFFIXE_COLLE = re.compile(r"\s*[TSN]{1,3}-\d{6}$")
PAT_REPORT = re.compile(r"^(\d{7}T)\s+(TN-\d{6})\s+TN-\d{6}\s+Report")          # compte collectif quelconque
PAT_COMPTE = re.compile(r"^(\d{7}T)\s+(?!TN-)\S")
PAT_TOTAL_COMPTE = re.compile(r"^Total\s+compte\s+(\d{7}T)\s+du")
PAT_BRUIT = re.compile(r"^Total\s+compte")
PAT_CUMULS = re.compile(r"^Cumuls?\s+avant\s+le\s+(\d{2}/\d{2}/\d{4})")
PAT_TX = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.+)$")
PAT_TOTAL_CLIENT = re.compile(r"^Total\s+(\d{7}T)\s+(TN-\d{6})\s+du")
PAT_TOTAL_GENERAL = re.compile(r"^Total\s+général")
PAT_PERIODE = re.compile(r"Date, de\s+\d{2}/\d{2}/\d{4}\s+à\s+(\d{2}/\d{2}/\d{4})")

# Montant Sage : milliers par espace, 3 décimales, négatif entre parenthèses.
PAT_AMOUNT = re.compile(r"(?<![\w,\-])\(?\d{1,3}(?:[ \u00a0]\d{3})*,\d{3}\)?")
PAT_LONG_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")


# ───────────────────────── Utilitaires ─────────────────────────
def get_bucket(jours_retard: int) -> str:
    if jours_retard <= 0:
        return "non_echu"
    if jours_retard <= 30:
        return "1-30"
    if jours_retard <= 60:
        return "31-60"
    if jours_retard <= 90:
        return "61-90"
    return "+90"


def clean_amount(s: str) -> float:
    """'1 234,567' -> 1234.567 ; '(1 234,567)' -> -1234.567"""
    if not s:
        return 0.0
    s = s.strip().replace(" ", "").replace("\u00a0", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def extract_amounts(line: str) -> List[Tuple[float, int]]:
    """Retourne [(valeur, position_début)] des montants de la ligne.
    Les dates à 4 chiffres sont neutralisées (même longueur) pour garder les positions."""
    masked = PAT_LONG_DATE.sub(lambda m: " " * len(m.group(0)), line)
    return [(clean_amount(m.group(0)), m.start()) for m in PAT_AMOUNT.finditer(masked)]


def nettoyer_libelle(texte: str) -> str:
    parts = texte.split(None, 1)          # 1er mot = code journal (BI3, VTE, CAI...)
    t = parts[1] if len(parts) > 1 else texte
    t = re.sub(r"\s*TN\d{2}-[A-Z0-9+]+\s?-\d{2}-\d{2}-\d{3}", "", t)   # n° de pièce
    t = re.sub(r"\s*\b[A-Z0-9]{2,4}-\d{4}\b", "", t)                   # BI3-2026
    t = re.sub(r"\s+B\s*$", "", t)                                      # type écriture B
    return re.sub(r"\s+", " ", t).strip()[:80] or "Écriture"


def nom_client(reste: str) -> str:
    n = PAT_SUFFIXE_EXACT.sub("", reste)
    if n == reste:
        n = PAT_SUFFIXE_COLLE.sub("", reste)
    return n.strip() or reste.strip()


def parse_date_ecr(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%y").date()


PAT_DEBUT_LOGIQUE = re.compile(
    r"^(\d{2}/\d{2}/\d{2}\s|TN-\d{6}\s|Cumuls?\s+avant|Total\s|\d{7}T\s)")


def fusionner_lignes(lines: Iterable[str]) -> List[str]:
    """Un libellé trop long peut être coupé sur 2 lignes par l'extraction PDF :
    '08/04/26 BI3 ... TN01-BI3-26-04-000' puis 'VIR RECU ... B 35 722,597 (53 266,409)'.
    On recolle les écritures dont la 1re ligne n'a pas ses montants."""
    out: List[str] = []
    attente: Optional[str] = None
    for raw in lines:
        line = " ".join(raw.split())
        if attente is not None:
            if line and not PAT_DEBUT_LOGIQUE.match(line):
                attente = f"{attente} {line}"
                if extract_amounts(attente):
                    out.append(attente)
                    attente = None
                continue
            out.append(attente)          # pas de suite : on garde telle quelle
            attente = None
        if PAT_TX.match(line) and not extract_amounts(line):      # 1 seul montant = valide (solde nul non imprimé)
            attente = line
        else:
            out.append(line)
    if attente is not None:
        out.append(attente)
    return out


# ───────────────────────── Étape 1 : lecture des lignes ─────────────────────────
def parser_lignes(lines: Iterable[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Transforme les lignes texte du Grand Livre en écritures par client."""
    clients: Dict[str, Dict[str, Any]] = {}
    meta: Dict[str, Any] = {"periode_fin": None, "total_general": None, "total_general_detail": None,
                            "totaux_pdf": {}, "totaux_detail": {}, "totaux_compte": {}, "ignorees": [],
                            "avertissements": []}
    compte: Optional[str] = None
    current: Optional[str] = None

    for raw in fusionner_lignes(lines):
        line = raw.strip()
        if not line:
            continue

        m = PAT_PERIODE.search(line)
        if m and not meta["periode_fin"]:
            meta["periode_fin"] = m.group(1)

        # Nouveau client
        m = PAT_CLIENT.match(line)
        if m:
            current = m.group(1)
            d = clients.setdefault(current, {"code": current, "nom": nom_client(m.group(2)), "lignes": [],
                                             "compte": compte or "4110001T", "comptes": set()})
            d["comptes"].add(compte or "4110001T")
            continue

        # Reprise d'un client sur une nouvelle page. NB : les montants de cette ligne
        # sont ceux de la page seulement -> ignorés.
        m = PAT_REPORT.match(line)
        if m:
            compte, current = m.group(1), m.group(2)
            continue
        m = PAT_COMPTE.match(line)
        if m:
            compte = m.group(1)
            continue

        # Total général du PDF (contrôle)
        if PAT_TOTAL_GENERAL.match(line):
            amts = extract_amounts(line)
            if amts:
                meta["total_general"] = amts[-1][0]
                meta["total_general_detail"] = [a for a, _ in amts]
            continue

        m = PAT_TOTAL_COMPTE.match(line)
        if m:
            meta["totaux_compte"][m.group(1)] = [a for a, _ in extract_amounts(line)]
            continue

        # Total client (contrôle)
        m = PAT_TOTAL_CLIENT.match(line)
        if m:
            amts = [a for a, _ in extract_amounts(line)]
            if amts:
                meta["totaux_pdf"][m.group(2)] = amts[-1]
                if len(amts) >= 3:
                    meta["totaux_detail"][(m.group(1), m.group(2))] = tuple(amts[-3:])
            if m.group(2) not in clients:
                meta["avertissements"].append(f"{m.group(2)} : en-tête client non reconnu")
            continue

        if not current:
            continue

        # Report à nouveau : le dernier montant est le solde cumulé (+ débit / – crédit)
        m = PAT_CUMULS.match(line)
        if m:
            amts = [a for a, _ in extract_amounts(line)]
            if not amts:
                continue
            solde = amts[-1]
            if len(amts) >= 3:
                debit, credit = amts[0], amts[1]
            else:
                debit, credit = (solde, 0.0) if solde >= 0 else (0.0, -solde)
            if abs(solde) < EPS and abs(debit) < EPS and abs(credit) < EPS:
                continue
            d = datetime.strptime(m.group(1), "%d/%m/%Y").date() - timedelta(days=1)  # solde au plus tard la veille
            clients[current]["lignes"].append({
                "report": True, "date": d, "libelle": f"Report à nouveau (avant le {m.group(1)})",
                "debit": debit, "credit": credit, "solde": solde, "net": solde,
            })
            continue

        # Écriture normale
        m = PAT_TX.match(line)
        if m:
            amts = extract_amounts(line)
            if not amts:
                meta["ignorees"].append({"code": current, "ligne": line[:120], "raison": "aucun montant lisible"})
                continue
            vals = [a for a, _ in amts]
            try:
                d = parse_date_ecr(m.group(1))
            except ValueError:
                meta["ignorees"].append({"code": current, "ligne": line[:120], "raison": "date invalide"})
                continue

            prev = clients[current]["lignes"][-1]["solde"] if clients[current]["lignes"] else 0.0
            if len(vals) >= 3:
                debit, credit, solde = vals[0], vals[1], vals[2]
            else:
                montant = vals[0]
                solde = vals[1] if len(vals) >= 2 else 0.0      # Sage n'imprime pas un solde nul
                diff = solde - prev
                if abs(diff - montant) < 0.01:
                    debit, credit = montant, 0.0
                elif abs(diff + montant) < 0.01:
                    debit, credit = 0.0, montant
                else:   # incohérence (ligne manquante ?) -> on déduit du signe et on alerte
                    debit, credit = (montant, 0.0) if diff > 0 else (0.0, montant)
                    meta["avertissements"].append(
                        f"{current} {m.group(1)} : solde incohérent (attendu {prev + (montant if diff > 0 else -montant):.3f}, lu {solde:.3f})")

            libelle = nettoyer_libelle(line[len(m.group(1)):][: amts[0][1] - len(m.group(1))])
            clients[current]["lignes"].append({
                "date": d, "libelle": libelle,
                "debit": debit, "credit": credit, "solde": solde, "net": debit - credit,
            })
        elif extract_amounts(line) and not PAT_BRUIT.match(line):
            meta["ignorees"].append({"code": current, "ligne": line[:120], "raison": "ligne avec montants non reconnue"})

    for c, d in clients.items():
        if len(d["comptes"]) > 1:
            meta["avertissements"].append(f"{c} {d['nom']} : présent dans plusieurs comptes collectifs ({', '.join(sorted(d['comptes']))}) – vérifier le rapprochement")
    return clients, meta


# ───────────────────────── Étape 2 : lettrage FIFO + ancienneté ─────────────────────────
def calculer_anciennete(lignes: List[Dict[str, Any]], date_ref: date, delai: int):
    """
    Les règlements (crédits) soldent les plus anciennes créances (FIFO).
    Un crédit en excès devient une avance qui vient réduire les débits suivants.
    Retourne (buckets, avance, reste_par_ligne).
    """
    ouverts: List[List[float]] = []     # créances ouvertes  [index_ligne, reste]
    avances: List[List[float]] = []     # crédits non affectés [index_ligne, reste]

    for i, l in enumerate(lignes):
        net = l["net"]
        if net > EPS:
            while net > EPS and avances:         # une facture éteint d'abord les avances les plus anciennes
                used = min(avances[0][1], net)
                avances[0][1] -= used
                net -= used
                if avances[0][1] <= EPS:
                    avances.pop(0)
            if net > EPS:
                ouverts.append([i, net])
        elif net < -EPS:
            a_payer = -net
            while a_payer > EPS and ouverts:
                used = min(ouverts[0][1], a_payer)
                ouverts[0][1] -= used
                a_payer -= used
                if ouverts[0][1] <= EPS:
                    ouverts.pop(0)
            if a_payer > EPS:
                avances.append([i, a_payer])

    buckets = {"non_echu": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "+90": 0.0}
    reste_ligne: Dict[int, Tuple[float, int, str]] = {}
    dont_report = 0.0
    for idx, reste in ouverts:
        if lignes[idx].get("report"):
            dont_report += reste
        echeance = lignes[idx]["date"] + timedelta(days=delai)
        jours = (date_ref - echeance).days
        b = get_bucket(jours)
        buckets[b] += reste
        reste_ligne[idx] = (reste, jours, b)
    # Avances / avoirs : ancienneté = jours écoulés depuis l'encaissement (min. 1 -> tranche 1-30)
    buckets_av = {k: 0.0 for k in buckets}
    for idx, reste in avances:
        jours = (date_ref - lignes[idx]["date"]).days
        b = get_bucket(max(jours, 1))
        buckets_av[b] += reste
        reste_ligne[idx] = (reste, jours, b)
    avance = sum(r for _, r in avances)
    return buckets, avance, reste_ligne, dont_report, buckets_av


# ───────────────────────── Étape 3 : assemblage ─────────────────────────
def construire_balance(clients, meta, date_ref: date, delai: int) -> BalanceAgeeResponse:
    avert: List[str] = list(meta["avertissements"])
    result: List[ClientBalance] = []
    exclus: List[Dict[str, Any]] = []
    total_report = 0.0
    totaux_av = {"non_echu": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "+90": 0.0}
    totaux = {"non_echu": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "+90": 0.0}

    for code, data in clients.items():
        lignes = data["lignes"]
        if not lignes:
            exclus.append({"code": code, "nom": data["nom"], "solde": 0.0, "raison": "Aucun mouvement sur la période"})
            continue
        solde_final = lignes[-1]["solde"]

        # Contrôle avec la ligne "Total 4110001T TN-xxxxxx" du PDF
        pdf_solde = meta["totaux_pdf"].get(code)
        if pdf_solde is not None and abs(pdf_solde - solde_final) > 0.01:
            avert.append(f"{code} {data['nom']} : solde calculé {solde_final:.3f} ≠ total PDF {pdf_solde:.3f}")
        if abs(solde_final) < SEUIL_SOLDE:
            exclus.append({"code": code, "nom": data["nom"], "solde": round(solde_final, 3), "raison": "Solde nul (|solde| < 0,100)"})
            continue

        buckets, avance, reste_ligne, dont_report, buckets_av = calculer_anciennete(lignes, date_ref, delai)

        details = []
        for i, l in enumerate(lignes):
            reste, jours, b = reste_ligne.get(i, (0.0, 0, ""))
            details.append(LigneTransaction(
                date=l["date"].strftime("%d/%m/%y"), libelle=l["libelle"],
                debit=round(l["debit"], 3), credit=round(l["credit"], 3),
                solde=round(l["solde"], 3), reste_du=round(reste, 3),
                jours_retard=jours, bucket=b,
                sens="C" if l["net"] < -EPS else ("D" if l["net"] > EPS else ""),
            ))

        # Invariant : après FIFO, créances ouvertes = solde si débiteur, sinon 0
        if abs(sum(buckets.values()) - max(solde_final, 0.0)) > 0.01:
            avert.append(f"{code} {data['nom']} : ventilation ({sum(buckets.values()):.3f}) ≠ solde ({solde_final:.3f})")
        if abs(sum(buckets_av.values()) - max(-solde_final, 0.0)) > 0.01:
            avert.append(f"{code} {data['nom']} : ventilation des avances ({sum(buckets_av.values()):.3f}) ≠ solde ({-solde_final:.3f})")
        for k in totaux_av:
            totaux_av[k] += buckets_av[k]
        total_report += dont_report
        for k in totaux:
            totaux[k] += buckets[k]
        result.append(ClientBalance(
            code=code, nom=data["nom"], total_solde=round(solde_final, 3),
            non_echu=round(buckets["non_echu"], 3), echu_30=round(buckets["1-30"], 3),
            echu_60=round(buckets["31-60"], 3), echu_90=round(buckets["61-90"], 3),
            echu_plus=round(buckets["+90"], 3), credit_non_affecte=round(avance, 3), dont_report=round(dont_report, 3),
            avance_buckets={k: round(v, 3) for k, v in buckets_av.items()},
            lignes=details,
        ))

    result.sort(key=lambda c: c.total_solde, reverse=True)
    total_general = round(sum(c.total_solde for c in result), 3)

    # Contrôle global (les clients à solde ~0 écartés n'ont qu'un impact négligeable)
    tg = meta["total_general"]
    if tg is not None and abs(tg - total_general) > 1:
        avert.append(f"Total général calculé {total_general:.3f} ≠ total PDF {tg:.3f}")

    total_deb = sum(c.total_solde for c in result if c.total_solde > 0)
    if total_report > 0 and total_deb > 0:
        avert.append(
            f"{total_report:,.3f} TND".replace(",", " ") + f" ({total_report / total_deb:.0%} des créances) proviennent du « report à nouveau » agrégé : "
            "leur ancienneté réelle est inconnue (comptée depuis le 31/12 précédent). "
            "Pour une balance exacte, relancez l'édition Sage avec « Écritures avant période en détail = Oui » "
            "ou une date de début plus ancienne.")
    controle = construire_controle(
        [{"code": c, "nom": d["nom"], "compte": d["compte"], "lignes": d["lignes"]} for c, d in clients.items()],
        meta["totaux_detail"], meta["totaux_compte"], meta["total_general_detail"], meta["ignorees"], exclus)
    controle["nb_affiches"] = len(result)
    if controle["statut"] != "OK":
        avert.insert(0, f"Contrôle d'extraction : {controle['nb_ecarts']} écart(s), {len(controle['non_reconnus'])} tiers non reconnu(s), "
                        f"{controle['nb_ignorees']} ligne(s) ignorée(s) – voir le détail du contrôle.")
    return BalanceAgeeResponse(
        controle=controle,
        date_reference=date_ref.strftime("%Y-%m-%d"),
        delai_paiement=delai,
        total_general=total_general,
        total_debiteur=round(sum(c.total_solde for c in result if c.total_solde > 0), 3),
        total_crediteur=round(sum(c.total_solde for c in result if c.total_solde < 0), 3),
        total_report=round(total_report, 3),
        totaux_avances={k: round(v, 3) for k, v in totaux_av.items()},
        totaux_buckets={k: round(v, 3) for k, v in totaux.items()},
        nb_clients=len(result),
        clients=result,
        avertissements=avert,
    )


def parser_pdf_sage(file_path: str, date_reference: Optional[date] = None,
                    delai_paiement: int = 0) -> BalanceAgeeResponse:
    lines: List[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                lines.extend(text.split("\n"))

    exiger_type(lines, "clients")
    clients, meta = parser_lignes(lines)

    if date_reference is None:   # défaut : fin de période imprimée sur le PDF, sinon aujourd'hui
        try:
            date_reference = datetime.strptime(meta["periode_fin"], "%d/%m/%Y").date()
        except (TypeError, ValueError):
            date_reference = date.today()

    return construire_balance(clients, meta, date_reference, delai_paiement)