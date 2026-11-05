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
    for agregat in agregats:
        for cle, valeur in agregat.items():
            if isinstance(valeur, (int, float)) and cle != "compte_banque":
                total[cle] += valeur
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

