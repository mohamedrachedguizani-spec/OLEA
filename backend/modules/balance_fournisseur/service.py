"""Balance âgée fournisseurs – Grand Livre auxiliaire Sage (4010000T / 4080000T / 4091000T).
Réutilise les briques génériques du module clients (montants, libellés, FIFO)."""
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pdfplumber

from modules.balance.service import (
    EPS, SEUIL_SOLDE, PAT_CLIENT, PAT_CUMULS, PAT_PERIODE, PAT_TX,
    calculer_anciennete, extract_amounts, nettoyer_libelle, nom_client,
)
from modules.balance.controle import construire_controle, exiger_type
from .models import BalanceFournisseurResponse, FournisseurBalance, LigneTransaction

C_DETTE, C_FNP, C_AVANCE = "4010000T", "4080000T", "4091000T"
ORDRE = (C_DETTE, C_FNP, C_AVANCE)
CODE_COURT = {C_DETTE: "401", C_FNP: "408", C_AVANCE: "409"}
BUCKET_KEYS = ("non_echu", "1-30", "31-60", "61-90", "+90")

PAT_COMPTE = re.compile(r"^(\d{7}T)\s+(?!TN-)\S")                      # "4010000T FOURNISSEURS"
PAT_REPORT = re.compile(r"^(\d{7}T)\s+(TN-\d{6})\s+TN-\d{6}\s+Report")
PAT_TOTAL_TIERS = re.compile(r"^Total\s+(\d{7}T)\s+(TN-\d{6})\s+du")
PAT_TOTAL_COMPTE = re.compile(r"^Total\s+compte\s+(\d{7}T)\s+du")
PAT_TOTAL_GENERAL = re.compile(r"^Total\s+général")
PAT_BRUIT = re.compile(r"^Total\s+compte")
PAT_DEBUT = re.compile(r"^(\d{2}/\d{2}/\d{2}\s|TN-\d{6}\s|\d{7}T\s|Cumuls?\s+avant|Total\s)")


def fusionner_lignes(lines: Iterable[str]) -> List[str]:
    """Recolle un libellé coupé sur 2 lignes (1re ligne SANS aucun montant).
    Une ligne avec un seul montant est valide : Sage n'imprime pas le solde cumulé quand il est nul."""
    out: List[str] = []
    attente: Optional[str] = None
    for raw in lines:
        line = " ".join(raw.split())
        if attente is not None:
            if line and not PAT_DEBUT.match(line):
                attente = f"{attente} {line}"
                if extract_amounts(attente):
                    out.append(attente)
                    attente = None
                continue
            out.append(attente)
            attente = None
        if PAT_TX.match(line) and not extract_amounts(line):
            attente = line
        else:
            out.append(line)
    if attente is not None:
        out.append(attente)
    return out


def parser_lignes(lines: Iterable[str]):
    tiers: Dict[str, Dict[str, Any]] = {}
    meta: Dict[str, Any] = {"periode_fin": None, "total_general": None, "totaux_tiers": {},
                            "totaux_compte": {}, "totaux_detail": {}, "totaux_compte_detail": {},
                            "total_general_detail": None, "ignorees": [], "avertissements": []}
    compte: Optional[str] = None
    code: Optional[str] = None

    for line in fusionner_lignes(lines):
        line = line.strip()
        if not line:
            continue
        m = PAT_PERIODE.search(line)
        if m and not meta["periode_fin"]:
            meta["periode_fin"] = m.group(1)

        m = PAT_REPORT.match(line)                 # reprise sur nouvelle page (montants ignorés)
        if m:
            compte, code = m.group(1), m.group(2)
            if code in tiers:
                tiers[code]["comptes"].setdefault(compte, [])
            continue
        m = PAT_COMPTE.match(line)                 # en-tête de compte collectif
        if m:
            compte, code = m.group(1), None
            continue
        m = PAT_CLIENT.match(line)                 # en-tête fournisseur
        if m:
            code = m.group(1)
            t = tiers.setdefault(code, {"code": code, "nom": nom_client(m.group(2)), "comptes": {}})
            t["comptes"].setdefault(compte, [])
            continue

        if PAT_TOTAL_GENERAL.match(line):
            amts = extract_amounts(line)
            if amts:
                meta["total_general"] = amts[-1][0]
                meta["total_general_detail"] = [a for a, _ in amts]
            continue
        m = PAT_TOTAL_COMPTE.match(line)
        if m:
            amts = extract_amounts(line)
            if amts:
                meta["totaux_compte"][m.group(1)] = amts[-1][0]
                meta["totaux_compte_detail"][m.group(1)] = [a for a, _ in amts]
            continue
        m = PAT_TOTAL_TIERS.match(line)
        if m:
            amts = extract_amounts(line)
            if amts:
                meta["totaux_tiers"][(m.group(1), m.group(2))] = amts[-1][0]
                if len(amts) >= 3:
                    meta["totaux_detail"][(m.group(1), m.group(2))] = tuple(a for a, _ in amts[-3:])
            if m.group(2) not in tiers:
                meta["avertissements"].append(f"{m.group(2)} : en-tête fournisseur non reconnu")
            continue

        if not code or code not in tiers or compte is None:
            continue
        lignes = tiers[code]["comptes"].setdefault(compte, [])

        m = PAT_CUMULS.match(line)                 # report à nouveau agrégé
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
            d = datetime.strptime(m.group(1), "%d/%m/%Y").date() - timedelta(days=1)   # au plus tard la veille
            lignes.append({"report": True, "date": d,
                           "libelle": f"Report à nouveau (avant le {m.group(1)})",
                           "debit": debit, "credit": credit, "solde": solde, "net": solde})
            continue

        m = PAT_TX.match(line)                     # écriture
        if m:
            amts = extract_amounts(line)
            if not amts:
                meta["ignorees"].append({"code": code, "ligne": line[:120], "raison": "aucun montant lisible"})
                continue
            vals = [a for a, _ in amts]
            try:
                d = datetime.strptime(m.group(1), "%d/%m/%y").date()
            except ValueError:
                meta["ignorees"].append({"code": code, "ligne": line[:120], "raison": "date invalide"})
                continue
            prev = lignes[-1]["solde"] if lignes else 0.0
            if len(vals) >= 3:
                debit, credit, solde = vals[0], vals[1], vals[2]
            else:
                montant = vals[0]
                solde = vals[1] if len(vals) >= 2 else 0.0      # solde nul = non imprimé
                diff = solde - prev
                if abs(diff - montant) < 0.01:
                    debit, credit = montant, 0.0
                elif abs(diff + montant) < 0.01:
                    debit, credit = 0.0, montant
                else:
                    debit, credit = (montant, 0.0) if diff > 0 else (0.0, montant)
                    meta["avertissements"].append(
                        f"{code} ({CODE_COURT.get(compte, compte)}) {m.group(1)} : solde incohérent (lu {solde:.3f}, attendu {prev + (montant if diff > 0 else -montant):.3f})")
            libelle = nettoyer_libelle(line[len(m.group(1)):][: amts[0][1] - len(m.group(1))])
            lignes.append({"date": d, "libelle": libelle, "debit": debit, "credit": credit,
                           "solde": solde, "net": debit - credit})
        elif extract_amounts(line) and not PAT_BRUIT.match(line):
            meta["ignorees"].append({"code": code, "ligne": line[:120], "raison": "ligne avec montants non reconnue"})
    return tiers, meta


def _r3(v: float) -> float:
    return round(v, 3) + 0.0        # évite -0.0


def construire_balance(tiers, meta, date_ref: date, delai: int) -> BalanceFournisseurResponse:
    avert: List[str] = list(meta["avertissements"])
    res: List[FournisseurBalance] = []
    exclus: List[Dict[str, Any]] = []
    totaux = {k: 0.0 for k in BUCKET_KEYS}
    totaux_av = {k: 0.0 for k in BUCKET_KEYS}
    total_report = 0.0
    somme_compte = {c: 0.0 for c in ORDRE}

    for code, t in tiers.items():
        soldes: Dict[str, float] = {}
        for compte, lignes in t["comptes"].items():
            if not lignes:
                continue
            s = lignes[-1]["solde"]
            soldes[compte] = s
            if compte in somme_compte:
                somme_compte[compte] += s
            pdf = meta["totaux_tiers"].get((compte, code))
            if pdf is not None and abs(pdf - s) > 0.01:
                avert.append(f"{code} {t['nom']} ({CODE_COURT.get(compte, compte)}) : solde calculé {s:.3f} ≠ total PDF {pdf:.3f}")

        dette = -soldes.get(C_DETTE, 0.0)          # + = nous devons
        fnp = -soldes.get(C_FNP, 0.0)
        avance = soldes.get(C_AVANCE, 0.0)         # + = avance versée
        if max(abs(dette), abs(fnp), abs(avance)) < SEUIL_SOLDE:
            sans_mvt = not any(t["comptes"].values())
            exclus.append({"code": code, "nom": t["nom"], "solde": _r3(dette),
                           "raison": "Aucun mouvement sur la période" if sans_mvt else "Soldes nuls (401 / 408 / 409)"})
            continue

        buckets = {k: 0.0 for k in BUCKET_KEYS}
        buckets_av = dict(buckets)
        reste_ligne: Dict[int, Any] = {}
        dont_report = non_impute = 0.0
        l401 = t["comptes"].get(C_DETTE) or []
        if l401:
            # côté dettes, le crédit est l'élément ouvert : on inverse le signe et on réutilise le FIFO clients
            flip = [{**l, "net": -l["net"]} for l in l401]
            buckets, non_impute, reste_ligne, dont_report, buckets_av = calculer_anciennete(flip, date_ref, delai)
            if abs(sum(buckets.values()) - max(dette, 0.0)) > 0.01:
                avert.append(f"{code} {t['nom']} : ventilation dettes ({sum(buckets.values()):.3f}) ≠ solde ({dette:.3f})")
            if abs(sum(buckets_av.values()) - max(-dette, 0.0)) > 0.01:
                avert.append(f"{code} {t['nom']} : ventilation non imputés ({sum(buckets_av.values()):.3f}) ≠ solde ({-dette:.3f})")

        details: List[LigneTransaction] = []
        for compte in ORDRE:
            for i, l in enumerate(t["comptes"].get(compte) or []):
                est401 = compte == C_DETTE
                reste, jours, b = reste_ligne.get(i, (0.0, 0, "")) if est401 else (0.0, 0, "")
                nf = -l["net"]
                sens = ("D" if nf > EPS else "C" if nf < -EPS else "") if est401 else ""
                details.append(LigneTransaction(
                    date=l["date"].strftime("%d/%m/%y"), libelle=l["libelle"], compte=CODE_COURT[compte],
                    debit=_r3(l["debit"]), credit=_r3(l["credit"]),
                    solde=_r3(l["solde"] if compte == C_AVANCE else -l["solde"]),
                    reste_du=_r3(reste), jours_retard=jours, sens=sens, bucket=b))

        for k in BUCKET_KEYS:
            totaux[k] += buckets[k]
            totaux_av[k] += buckets_av[k]
        total_report += dont_report
        res.append(FournisseurBalance(
            code=code, nom=t["nom"], total_solde=_r3(dette),
            non_echu=_r3(buckets["non_echu"]), echu_30=_r3(buckets["1-30"]), echu_60=_r3(buckets["31-60"]),
            echu_90=_r3(buckets["61-90"]), echu_plus=_r3(buckets["+90"]),
            credit_non_affecte=_r3(non_impute), avance_buckets={k: _r3(v) for k, v in buckets_av.items()},
            dont_report=_r3(dont_report), fnp=_r3(fnp), avance_409=_r3(avance), lignes=details))

    res.sort(key=lambda f: f.total_solde, reverse=True)

    for compte, somme in somme_compte.items():
        pdf = meta["totaux_compte"].get(compte)
        if pdf is not None and abs(pdf - somme) > 1:
            avert.append(f"Compte {CODE_COURT[compte]} : total calculé {somme:.3f} ≠ total PDF {pdf:.3f}")

    total_general = _r3(sum(f.total_solde for f in res))
    total_dettes = _r3(sum(f.total_solde for f in res if f.total_solde > 0))
    total_fnp = _r3(sum(f.fnp for f in res))
    total_avances = _r3(sum(f.avance_409 for f in res))
    total_net = _r3(total_general + total_fnp - total_avances)
    tg = meta["total_general"]
    if tg is not None and abs(-tg - total_net) > 1:
        avert.append(f"Total net calculé {total_net:.3f} ≠ total général PDF {-tg:.3f}")

    if total_report > 0 and total_dettes > 0:
        avert.append(
            f"{total_report:,.3f} TND".replace(",", " ") + f" ({total_report / total_dettes:.0%} des dettes) proviennent du « report à nouveau » agrégé : "
            "leur ancienneté réelle est inconnue (comptée depuis le 31/12 précédent). "
            "Relancez l'édition Sage avec « Écritures avant période en détail = Oui » pour une balance exacte.")
    avert.append("Les comptes 408 (factures non parvenues) et 409 (avances versées) sont présentés à part : ils ne sont pas compensés dans la balance âgée des dettes (compte 401).")

    controle = construire_controle(
        [{"code": c, "nom": t["nom"], "compte": cp, "lignes": lg} for c, t in tiers.items() for cp, lg in t["comptes"].items()],
        meta["totaux_detail"], meta["totaux_compte_detail"], meta["total_general_detail"], meta["ignorees"], exclus,
        lambda c: CODE_COURT.get(c, c))
    controle["nb_affiches"] = len(res)
    if controle["statut"] != "OK":
        avert.insert(0, f"Contrôle d'extraction : {controle['nb_ecarts']} écart(s), {len(controle['non_reconnus'])} tiers non reconnu(s), "
                        f"{controle['nb_ignorees']} ligne(s) ignorée(s) – voir le détail du contrôle.")
    return BalanceFournisseurResponse(
        controle=controle,
        date_reference=date_ref.strftime("%Y-%m-%d"), delai_paiement=delai,
        total_general=total_general, total_dettes=total_dettes,
        total_non_imputes=_r3(sum(f.total_solde for f in res if f.total_solde < 0)),
        total_fnp=total_fnp, total_avances=total_avances, total_net=total_net, total_report=_r3(total_report),
        totaux_buckets={k: _r3(v) for k, v in totaux.items()},
        totaux_avances={k: _r3(v) for k, v in totaux_av.items()},
        nb_fournisseurs=len(res), fournisseurs=res, avertissements=avert)


def parser_pdf_fournisseur(file_path: str, date_reference: Optional[date] = None,
                           delai_paiement: int = 0) -> BalanceFournisseurResponse:
    lines: List[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                lines.extend(text.split("\n"))
    exiger_type(lines, "fournisseurs")
    tiers, meta = parser_lignes(lines)
    if date_reference is None:
        try:
            date_reference = datetime.strptime(meta["periode_fin"], "%d/%m/%Y").date()
        except (TypeError, ValueError):
            date_reference = date.today()
    return construire_balance(tiers, meta, date_reference, delai_paiement)