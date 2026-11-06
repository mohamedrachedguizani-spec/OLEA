# modules/tresorerie/service.py
"""Calculs du module Trésorerie, sans accès base de données (testables)."""

from typing import Dict, List, Optional

from .constants import (
    BANQUES_TRESORERIE,
    NATURE_COMMISSION,
    NATURE_EXPLOITATION,
    NATURE_HORS_EXPLOITATION,
    NATURE_LABELS,
    suggerer_nature,
)


def _montant(valeur) -> float:
    try:
        return float(valeur or 0)
    except (TypeError, ValueError):
        return 0.0


def libelle_banque(compte_banque: str) -> Optional[str]:
    banque = BANQUES_TRESORERIE.get((compte_banque or "").strip().upper())
    return banque["libelle"] if banque else None


def nouveau_agregat(compte_banque: str) -> dict:
    return {
        "compte_banque": compte_banque,
        "libelle_banque": libelle_banque(compte_banque),
        "recette_exploitation": 0.0,
        "dont_recette_commission": 0.0,
        "depense_exploitation": 0.0,
        "dont_depense_commission": 0.0,
        "tresorerie_nette_exploitation": 0.0,
        "recette_hors_exploitation": 0.0,
        "depense_hors_exploitation": 0.0,
        "tresorerie_nette_hors_exploitation": 0.0,
        "non_classe_count": 0,
        "non_classe_debit": 0.0,
        "non_classe_credit": 0.0,
        "total_debit": 0.0,
        "total_credit": 0.0,
        "nb_mouvements": 0,
        "solde_ouverture": None,
        "solde_ouverture_date": None,
        "solde": None,
    }


def _arrondir(valeur: float) -> float:
    return round(valeur, 3)


def _finaliser_agregat(agregat: dict) -> dict:
    """Applique les ratios dérivés et arrondit les montants.

    Convention retenue (sens bancaire du relevé) :
      - crédit = entrée d'argent = recette ;
      - débit  = sortie d'argent = dépense.
    Les commissions sont comptées dans la trésorerie d'exploitation
    (recette ou dépense selon leur sens), d'où le ratio :
      recette exploitation = crédits exploitation + crédits commission
      dépense exploitation = débits exploitation + débits commission
    """
    agregat["recette_exploitation"] = _arrondir(agregat["recette_exploitation"])
    agregat["depense_exploitation"] = _arrondir(agregat["depense_exploitation"])
    agregat["dont_recette_commission"] = _arrondir(agregat["dont_recette_commission"])
    agregat["dont_depense_commission"] = _arrondir(agregat["dont_depense_commission"])
    agregat["recette_hors_exploitation"] = _arrondir(agregat["recette_hors_exploitation"])
    agregat["depense_hors_exploitation"] = _arrondir(agregat["depense_hors_exploitation"])
    agregat["non_classe_debit"] = _arrondir(agregat["non_classe_debit"])
    agregat["non_classe_credit"] = _arrondir(agregat["non_classe_credit"])
    agregat["total_debit"] = _arrondir(agregat["total_debit"])
    agregat["total_credit"] = _arrondir(agregat["total_credit"])
    agregat["tresorerie_nette_exploitation"] = _arrondir(
        agregat["recette_exploitation"] - agregat["depense_exploitation"]
    )
    agregat["tresorerie_nette_hors_exploitation"] = _arrondir(
        agregat["recette_hors_exploitation"] - agregat["depense_hors_exploitation"]
    )
    if agregat.get("solde") is not None:
        agregat["solde"] = _arrondir(agregat["solde"])
    if agregat.get("solde_ouverture") is not None:
        agregat["solde_ouverture"] = _arrondir(agregat["solde_ouverture"])
    return agregat


def cumuler_mouvement(agregat: dict, mouvement: dict) -> None:
    """Ajoute un mouvement aux totaux d'un agrégat banque."""
    debit = _montant(mouvement.get("debit"))
    credit = _montant(mouvement.get("credit"))
    nature = (mouvement.get("nature") or "").strip() or None

    agregat["total_debit"] += debit
    agregat["total_credit"] += credit
    agregat["nb_mouvements"] += 1

    if nature == NATURE_COMMISSION:
        agregat["dont_recette_commission"] += credit
        agregat["dont_depense_commission"] += debit
        agregat["recette_exploitation"] += credit
        agregat["depense_exploitation"] += debit
    elif nature == NATURE_EXPLOITATION:
        agregat["recette_exploitation"] += credit
        agregat["depense_exploitation"] += debit
    elif nature == NATURE_HORS_EXPLOITATION:
        agregat["recette_hors_exploitation"] += credit
        agregat["depense_hors_exploitation"] += debit
    else:
        agregat["non_classe_count"] += 1
        agregat["non_classe_debit"] += debit
        agregat["non_classe_credit"] += credit


def totaliser(agregats: List[dict]) -> dict:
    """Somme des agrégats de toutes les banques (ratio « toutes banques »)."""
    total = nouveau_agregat("TOUTES")
    total["libelle_banque"] = "Toutes banques"
    # Champs calculés à part : le solde se cumule uniquement sur les banques qui
    # en ont un, et sa date n'a pas de sens au niveau global.
    hors_somme = {"compte_banque", "solde", "solde_ouverture", "solde_ouverture_date"}
    soldes, ouvertures = [], []
    for agregat in agregats:
        for cle, valeur in agregat.items():
            if cle in hors_somme:
                continue
            if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
                total[cle] += valeur
        if agregat.get("compte_banque") in ("TOUTES", "Autre"):
            continue
        if agregat.get("solde") is not None:
            soldes.append(agregat["solde"])
        if agregat.get("solde_ouverture") is not None:
            ouvertures.append(agregat["solde_ouverture"])
    # Solde total : les comptes en devises sont déjà convertis en TND à l'import,
    # la somme est donc homogène. `solde` reste None si aucune banque n'a de solde.
    total["solde"] = round(sum(soldes), 3) if soldes else None
    total["solde_ouverture"] = round(sum(ouvertures), 3) if ouvertures else None
    return _finaliser_agregat(total)


def construire_reporting(mouvements: List[dict]) -> List[dict]:
    """Agrège les mouvements par banque, banques sans mouvement incluses.

    Chaque mouvement est un dict avec au moins : compte_banque, debit, credit, nature.
    Les banques présentes dans le référentiel mais sans mouvement apparaissent
    avec des zéros, pour que le reporting reste lisible d'une page à l'autre.
    """
    agrégats: Dict[str, dict] = {
        code: nouveau_agregat(code) for code in BANQUES_TRESORERIE
    }
    for mouvement in mouvements:
        code = (mouvement.get("compte_banque") or "").strip() or "Autre"
        if code not in agrégats:
            agrégats[code] = nouveau_agregat(code)
        cumuler_mouvement(agrégats[code], mouvement)

    # Ordre du référentiel, puis banques inconnues par ordre alphabétique.
    ordre = list(BANQUES_TRESORERIE.keys())
    tri = sorted(
        agrégats.values(),
        key=lambda a: (
            ordre.index(a["compte_banque"]) if a["compte_banque"] in ordre else len(ordre),
            a["compte_banque"],
        ),
    )
    return [_finaliser_agregat(agregat) for agregat in tri]


def construire_controle_extraction(
    fichier: str,
    format_detecte: str,
    lignes_source: int,
    mouvements: List[dict],
    messages: Optional[List[str]] = None,
) -> dict:
    """Contrôle d'extraction au même format que la saisie bancaire."""
    total_debit = round(sum(_montant(m.get("debit")) for m in mouvements), 3)
    total_credit = round(sum(_montant(m.get("credit")) for m in mouvements), 3)
    lignes_ignorees = max(0, lignes_source - len(mouvements))
    alertes = list(messages or [])
    if lignes_ignorees:
        alertes.append(f"{lignes_ignorees} ligne(s) ignorée(s) ou non interprétée(s).")
    return {
        "statut": "WARNING" if alertes else "OK",
        "fichier": fichier,
        "format_detecte": (format_detecte or "unknown").upper(),
        "lignes_source": lignes_source,
        "lignes_extraites": len(mouvements),
        "lignes_ignorees": lignes_ignorees,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "messages": alertes,
    }


def preparer_mouvements_extraits(mouvements: List[dict]) -> List[dict]:
    """Ajoute à chaque mouvement sa nature suggérée (jamais appliquée d'office)."""
    prepares = []
    for mouvement in mouvements:
        nature_suggeree = suggerer_nature(
            mouvement.get("libelle"), _montant(mouvement.get("debit")), _montant(mouvement.get("credit"))
        )
        prepares.append({**mouvement, "nature_suggeree": nature_suggeree})
    return prepares


def libelle_nature(nature: Optional[str]) -> Optional[str]:
    return NATURE_LABELS.get(nature) if nature else None


def periodes_chevauchent(debut_a, fin_a, debut_b, fin_b) -> bool:
    """Deux plages inclusives [a, b] et [c, d] se chevauchent-elles ?

    Une date absente (import ancien sans période) ne peut pas être comparée :
    on la considère comme non chevauchante pour ne pas bloquer l'import.
    """
    if not all((debut_a, fin_a, debut_b, fin_b)):
        return False
    return debut_a <= fin_b and debut_b <= fin_a


def filtrer_mouvements_par_periode(mouvements: List[dict], date_debut, date_fin):
    """Sépare les mouvements dans [date_debut, date_fin] de ceux hors période.

    La période est inclusive des deux bornes. Un mouvement sans date lisible
    est considéré hors période.
    """
    dans, hors = [], []
    for mouvement in mouvements:
        date_mouvement = mouvement.get("date_operation")
        if date_mouvement is not None and date_debut <= date_mouvement <= date_fin:
            dans.append(mouvement)
        else:
            hors.append(mouvement)
    return dans, hors


# ─── Solde par banque ───

def ancre_de_banque(ancres: List[dict], compte_banque: str, date_reference=None) -> Optional[dict]:
    """Ancre de solde d'une banque, si elle est déjà valable à `date_reference`.

    L'ancre fige le solde de départ d'une banque : elle est lue une seule fois
    sur le premier extrait importé, puis conservée indépendamment des imports.
    Une ancre postérieure à la date du rapport ne permet pas de calculer un
    solde pour cette période : mieux vaut « non disponible » qu'un chiffre faux.
    """
    code = (compte_banque or "").strip()
    for ancre in ancres:
        if (ancre.get("compte_banque") or "").strip() != code:
            continue
        date_solde = ancre.get("date_solde")
        if date_reference and date_solde and date_solde > date_reference:
            return None
        return ancre
    return None


def choisir_ancre_solde(imports: List[dict], date_fin=None) -> dict:
    """Rétrocompatibilité : ancre déduite de l'ancien stockage par import.

    N'est plus utilisée pour le calcul (voir ancre_de_banque), mais reste
    disponible pour d'éventuels scripts de reprise des soldes existants.
    """
    par_banque: Dict[str, dict] = {}
    for imp in imports:
        code = (imp.get("compte_banque") or "").strip()
        if not code or imp.get("solde_ouverture") is None:
            continue
        debut = imp.get("periode_debut")
        if date_fin and debut and debut > date_fin:
            continue
        courant = par_banque.get(code)
        if courant is None:
            par_banque[code] = imp
            continue
        debut_courant = courant.get("periode_debut")
        if debut is not None and (debut_courant is None or debut < debut_courant):
            par_banque[code] = imp
    return par_banque


def demarrer_couverture(ancre: dict):
    """Date à partir de laquelle le solde de départ est valable."""
    return ancre.get("date_solde") or ancre.get("solde_ouverture_date") or ancre.get("periode_debut")


def calculer_solde(solde_ouverture, mouvements_nets) -> "float | None":
    """Solde = solde de départ de l'ancre + mouvements (crédits − débits) depuis lors."""
    if solde_ouverture is None:
        return None
    try:
        return round(float(solde_ouverture) + float(mouvements_nets or 0), 3)
    except (TypeError, ValueError):
        return None


def totaliser_commissions(banques: List[dict]) -> dict:
    """Synthèse des commissions bancaires, banque par banque puis au total."""
    par_banque = []
    total_encaissees = 0.0
    total_payees = 0.0
    for banque in banques:
        encaissees = round(float(banque.get("dont_recette_commission") or 0), 3)
        payees = round(float(banque.get("dont_depense_commission") or 0), 3)
        total_encaissees += encaissees
        total_payees += payees
        par_banque.append({
            "compte_banque": banque.get("compte_banque"),
            "libelle_banque": banque.get("libelle_banque"),
            "commissions_encaissees": encaissees,
            "commissions_payees": payees,
            "total_commissions": round(encaissees + payees, 3),
            "commissions_nettes": round(encaissees - payees, 3),
            "nb_mouvements": int(banque.get("nb_mouvements") or 0),
        })
    return {
        "par_banque": par_banque,
        "total_encaissees": round(total_encaissees, 3),
        "total_payees": round(total_payees, 3),
        "total_commissions": round(total_encaissees + total_payees, 3),
        "total_nettes": round(total_encaissees - total_payees, 3),
    }

