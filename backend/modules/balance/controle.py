"""Contrôle d'intégrité de l'extraction d'un Grand Livre auxiliaire Sage.

Principe : pour chaque tiers, Sage imprime une ligne « Total <compte> <tiers> » (débit, crédit, solde).
On la compare à la somme des écritures réellement extraites. Une écriture perdue, dupliquée ou mal
attribuée fait apparaître un écart. Les contrôles sont aussi faits par compte collectif et au total général.
"""
import re
from typing import Any, Callable, Dict, Iterable, List

TOL = 0.011        # tolérance par tiers (arrondi à 3 décimales)
TOL_AGREGE = 0.5   # tolérance sur les totaux de compte / général (cumul d'arrondis)


def _ecart(code, nom, compte, champ, calcule, pdf, **extra) -> Dict[str, Any]:
    return {"code": code, "nom": nom, "compte": compte, "champ": champ,
            "calcule": round(calcule, 3), "pdf": round(pdf, 3), "ecart": round(calcule - pdf, 3), **extra}


def construire_controle(sous_comptes: List[Dict[str, Any]], totaux_detail: Dict, totaux_compte: Dict,
                        total_general, ignorees: List[Dict[str, Any]], exclus: List[Dict[str, Any]],
                        libelle_compte: Callable[[str], str] = lambda c: c) -> Dict[str, Any]:
    """sous_comptes : [{code, nom, compte, lignes:[{date, debit, credit, solde, net}]}]
    totaux_detail  : {(compte, code): (débit, crédit, solde)} lus sur les lignes « Total » du PDF
    totaux_compte  : {compte: [montants]}   total_general : [montants] ou None"""
    ecarts: List[Dict[str, Any]] = []
    detail: List[Dict[str, Any]] = []
    index = set()
    nb_lignes = 0
    par_compte: Dict[str, List[float]] = {}
    general = [0.0, 0.0, 0.0]

    for sc in sous_comptes:
        code, nom, compte, lignes = sc["code"], sc["nom"], sc["compte"], sc["lignes"]
        index.add((compte, code))
        nb_lignes += len(lignes)
        deb = sum(l["debit"] for l in lignes)
        cre = sum(l["credit"] for l in lignes)
        sol = lignes[-1]["solde"] if lignes else 0.0
        ok = True

        prev = 0.0                                     # enchaînement : solde précédent + mouvement = solde lu
        for l in lignes:
            if abs(prev + l["net"] - l["solde"]) > TOL:
                ok = False
                ecarts.append(_ecart(code, nom, libelle_compte(compte), "enchaînement du solde",
                                     prev + l["net"], l["solde"], date=l["date"].strftime("%d/%m/%y")))
            prev = l["solde"]

        pdf = totaux_detail.get((compte, code))
        if pdf is not None:
            for champ, calc, ref in (("débit", deb, pdf[0]), ("crédit", cre, pdf[1]), ("solde", sol, pdf[2])):
                if abs(calc - ref) > TOL:
                    ok = False
                    ecarts.append(_ecart(code, nom, libelle_compte(compte), champ, calc, ref))
        detail.append({"code": code, "nom": nom, "compte": libelle_compte(compte), "nb_lignes": len(lignes),
                       "debit": round(deb, 3), "credit": round(cre, 3), "solde": round(sol, 3),
                       "pdf_debit": None if pdf is None else round(pdf[0], 3),
                       "pdf_credit": None if pdf is None else round(pdf[1], 3),
                       "pdf_solde": None if pdf is None else round(pdf[2], 3),
                       "ok": ok and pdf is not None})
        s = par_compte.setdefault(compte, [0.0, 0.0, 0.0])
        for i, v in enumerate((deb, cre, sol)):
            s[i] += v
            general[i] += v

    # Tiers imprimés (ligne Total) mais jamais reconnus à l'extraction -> écritures potentiellement perdues
    non_reconnus = [{"code": code, "compte": libelle_compte(compte), "debit": a[0], "credit": a[1], "solde": a[2]}
                    for (compte, code), a in totaux_detail.items()
                    if (compte, code) not in index and any(abs(x) > 0.0005 for x in a)]

    for compte, a in (totaux_compte or {}).items():            # totaux de compte collectif
        s = par_compte.get(compte, [0.0, 0.0, 0.0])
        if len(a) >= 3:
            for champ, calc, ref in (("débit", s[0], a[-3]), ("crédit", s[1], a[-2]), ("solde", s[2], a[-1])):
                if abs(calc - ref) > TOL_AGREGE:
                    ecarts.append(_ecart("TOTAL", f"Total compte {libelle_compte(compte)}", libelle_compte(compte), champ, calc, ref))
    if total_general and len(total_general) >= 3:                # total général
        for champ, calc, ref in (("débit", general[0], total_general[-3]), ("crédit", general[1], total_general[-2]),
                                 ("solde", general[2], total_general[-1])):
            if abs(calc - ref) > TOL_AGREGE:
                ecarts.append(_ecart("TOTAL", "Total général", "", champ, calc, ref))

    ok_global = not ecarts and not non_reconnus and not ignorees
    return {
        "statut": "OK" if ok_global else "ANOMALIES",
        "nb_tiers_pdf": len({code for (_, code) in totaux_detail}),
        "nb_sous_comptes_pdf": len(totaux_detail),
        "nb_sous_comptes_lus": len(sous_comptes),
        "nb_lignes": nb_lignes,
        "nb_ecarts": len(ecarts), "ecarts": ecarts[:100],
        "non_reconnus": non_reconnus,
        "nb_ignorees": len(ignorees), "ignorees": ignorees[:50],
        "exclus": exclus,
        "detail": detail,
        "totaux_lus": {"debit": round(general[0], 3), "credit": round(general[1], 3), "solde": round(general[2], 3)},
        "totaux_pdf": None if not total_general or len(total_general) < 3 else
        {"debit": total_general[-3], "credit": total_general[-2], "solde": total_general[-1]},
    }


class TypeGrandLivreInvalide(ValueError):
    """Le PDF n'est pas du type attendu (clients / fournisseurs)."""


_PAT_FRS = re.compile(r"^40\d{5}T\s")
_PAT_CLT = re.compile(r"^41\d{5}T\s")


def detecter_type(lines: Iterable[str]) -> str:
    """'fournisseurs' (comptes 40xxxxxT), 'clients' (41xxxxxT), 'mixte' ou 'inconnu'."""
    frs = clt = False
    for raw in lines:
        l = " ".join(raw.split())
        frs = frs or bool(_PAT_FRS.match(l))
        clt = clt or bool(_PAT_CLT.match(l))
    return "mixte" if frs and clt else "fournisseurs" if frs else "clients" if clt else "inconnu"


def exiger_type(lines: Iterable[str], attendu: str) -> None:
    lignes = list(lines)
    trouve = detecter_type(lignes)
    if trouve in ("fournisseurs", "clients") and trouve != attendu:
        raise TypeGrandLivreInvalide(
            f"Ce PDF est un Grand Livre auxiliaire {trouve}, alors que cette page attend un Grand Livre {attendu}. "
            f"Utilisez la page « Balance âgée {trouve} ».")