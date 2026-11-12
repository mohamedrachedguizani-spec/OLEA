# modules/tresorerie/service.py
"""Calculs du module Trésorerie, sans accès base de données (testables)."""

from datetime import timedelta
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
        # Cumul des deux nets : la trésorerie réellement dégagée sur la période.
        "tresorerie_nette_globale": 0.0,
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
    # Net global = les deux nets additionnés. C'est le total des recettes moins
    # le total des dépenses de la période, tous types confondus.
    agregat["tresorerie_nette_globale"] = _arrondir(
        agregat["tresorerie_nette_exploitation"] + agregat["tresorerie_nette_hors_exploitation"]
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



# ─── Analyse graphique (recette/dépense par période, solde par jour) ───

GRANULARITES_ANALYSE = ("jour", "semaine", "mois")


def normaliser_granularite(valeur) -> str:
    """Retourne « jour », « semaine » ou « mois ». Lève ValueError sinon."""
    granularite = (valeur or "jour").strip().lower()
    if granularite not in GRANULARITES_ANALYSE:
        raise ValueError(
            "Granularité invalide : valeurs attendues " + ", ".join(GRANULARITES_ANALYSE)
        )
    return granularite


def cle_periode(date_valeur, granularite: str):
    """Clé de regroupement d'une date selon la granularité demandée.

    Le jour est rendu tel quel ; la semaine est ramenée à son lundi (ISO) ; le
    mois à son premier jour. Ramener chaque clé sur une date réelle permet de
    trier et d'espacer l'axe des temps sans conversion supplémentaire.
    """
    if date_valeur is None:
        return None
    if granularite == "jour":
        return date_valeur
    if granularite == "semaine":
        return date_valeur - timedelta(days=date_valeur.weekday())
    if granularite == "mois":
        return date_valeur.replace(day=1)
    raise ValueError("Granularité invalide : " + str(granularite))


def agreger_flux_par_periode(mouvements: List[dict], granularite: str = "jour",
                             compte_banque: Optional[str] = None) -> List[dict]:
    """Recette / dépense par période et par banque.

    Un mouvement est une recette s'il porte un crédit, une dépense s'il porte un
    débit. Les mouvements de commissions et hors exploitation comptent comme les
    autres : les graphiques décrivent la trésorerie réelle, pas les seuls ratios
    d'exploitation.
    """
    granularite = normaliser_granularite(granularite)
    code_filtre = (compte_banque or "").strip().upper() or None

    periodes: Dict[object, dict] = {}
    for mouvement in mouvements:
        code = (mouvement.get("compte_banque") or "").strip() or "Autre"
        if code_filtre and code != code_filtre:
            continue
        cle = cle_periode(mouvement.get("date_operation"), granularite)
        if cle is None:
            continue
        debit = _montant(mouvement.get("debit"))
        credit = _montant(mouvement.get("credit"))

        entree = periodes.setdefault(cle, {"periode": cle, "par_banque": {}, "total": {
            "recette": 0.0, "depense": 0.0, "nb_mouvements": 0,
        }})
        banque = entree["par_banque"].setdefault(code, {
            "recette": 0.0, "depense": 0.0, "nb_mouvements": 0,
        })
        banque["recette"] += credit
        banque["depense"] += debit
        banque["nb_mouvements"] += 1
        entree["total"]["recette"] += credit
        entree["total"]["depense"] += debit
        entree["total"]["nb_mouvements"] += 1

    resultat = []
    for cle in sorted(periodes):
        entree = periodes[cle]
        par_banque = {
            code: {
                "recette": round(valeurs["recette"], 3),
                "depense": round(valeurs["depense"], 3),
                "net": round(valeurs["recette"] - valeurs["depense"], 3),
                "nb_mouvements": valeurs["nb_mouvements"],
            }
            for code, valeurs in entree["par_banque"].items()
        }
        resultat.append({
            "periode": cle,
            "par_banque": par_banque,
            "recette": round(entree["total"]["recette"], 3),
            "depense": round(entree["total"]["depense"], 3),
            "net": round(entree["total"]["recette"] - entree["total"]["depense"], 3),
            "nb_mouvements": entree["total"]["nb_mouvements"],
        })
    return resultat


def construire_serie_soldes(mouvements: List[dict], ancres: dict,
                            date_debut=None, date_fin=None) -> dict:
    """Solde de chaque banque, jour par jour, depuis son ancre.

    Le solde suit la règle du reporting : solde figé de l'ancre + mouvements
    cumulés depuis la date de l'ancre. Une banque sans ancre n'a pas de courbe
    (jamais une courbe à zéro, qui laisserait croire à un compte vide).

    Les jours sans mouvement reprennent la dernière valeur connue : la courbe
    reste continue au lieu de redescendre à zéro entre deux opérations.

    `ancres` est un dict {compte_banque: {"solde": float, "date_solde": date}}.
    Retourne {"series": {banque: [{date, solde}]}, "sans_solde": [codes]}.
    """
    codes = sorted({
        (m.get("compte_banque") or "").strip()
        for m in mouvements
        if (m.get("compte_banque") or "").strip()
    })
    for code in ancres:
        code_propre = (code or "").strip()
        if code_propre and code_propre not in codes:
            codes.append(code_propre)

    series: Dict[str, List[dict]] = {}
    sans_solde: List[str] = []

    for code in codes:
        ancre = ancres.get(code)
        solde_initial = ancre.get("solde") if ancre else None
        date_ancre = ancre.get("date_solde") if ancre else None
        if solde_initial is None or date_ancre is None:
            sans_solde.append(code)
            continue
        # Ancre postérieure à la date d'arrêtée : le solde de la banque n'est pas
        # encore connu à cette date. Mieux vaut ne pas tracer plutôt qu'afficher
        # une courbe qui ne rejoint pas le solde du reporting.
        if date_fin is not None and date_ancre > date_fin:
            sans_solde.append(code)
            continue

        # Mouvements de la banque depuis l'ancre, agrégés par jour.
        nets_par_jour: Dict[object, float] = {}
        for mouvement in mouvements:
            if (mouvement.get("compte_banque") or "").strip() != code:
                continue
            date_mouvement = mouvement.get("date_operation")
            if date_mouvement is None or date_mouvement < date_ancre:
                continue
            if date_fin is not None and date_mouvement > date_fin:
                continue
            nets_par_jour[date_mouvement] = (
                nets_par_jour.get(date_mouvement, 0.0)
                + _montant(mouvement.get("credit"))
                - _montant(mouvement.get("debit"))
            )

        if not nets_par_jour:
            series[code] = [{"date": date_ancre, "solde": round(float(solde_initial), 3)}]
            continue

        # La courbe démarre à la date de l'ancre (point de départ), ou plus tard
        # si le filtre « Du » commence après elle. Les mouvements antérieurs à ce
        # point sont déjà intégrés dans le solde de départ calculé ci-dessous.
        debut = date_ancre
        if date_debut is not None and date_debut > debut:
            debut = date_debut
        # Le solde est arrêté à la borne « Au » : la courbe s'y arrête même si le
        # dernier mouvement est antérieur, la dernière valeur y est reportée.
        if date_fin is not None:
            fin = max(date_fin, debut)
        else:
            fin = max(max(nets_par_jour), debut)

        points = []
        # Solde de fin de journée : on part de l'ancre et on applique le net du
        # jour avant d'émettre le point, pour que le dernier jour de la courbe
        # tombe exactement sur le solde affiché par le reporting (KPI).
        # La boucle part de l'ancre et traverse tous les jours jusqu'à `debut` :
        # les mouvements antérieurs au filtre « Du » sont ainsi intégrés une
        # seule fois, en avançant jour après jour.
        solde_courant = float(solde_initial)
        jour_courant = date_ancre
        while jour_courant <= fin:
            solde_courant += nets_par_jour.get(jour_courant, 0.0)
            if jour_courant >= debut:
                points.append({"date": jour_courant, "solde": round(solde_courant, 3)})
            jour_courant += timedelta(days=1)
        series[code] = points

    return {"series": series, "sans_solde": sans_solde}


def echantillonner_serie(points: List[dict], granularite: str = "jour") -> List[dict]:
    """Ramène une série journalière à la granularité demandée.

    On conserve le **dernier** solde de chaque période : le solde d'une semaine
    ou d'un mois est celui de sa clôture, pas celui de son premier jour. La date
    renvoyée est la clé de période (lundi pour une semaine, 1er pour un mois),
    exactement celle utilisée par les barres recette/dépense : les deux
    graphiques partagent donc la même échelle de dates.
    """
    granularite = normaliser_granularite(granularite)
    if granularite == "jour" or not points:
        return list(points)

    derniers = {}
    for point in points:
        cle = cle_periode(point.get("date"), granularite)
        if cle is None:
            continue
        # Les points arrivent triés : le dernier vu pour une clé porte le solde
        # de clôture de la période.
        derniers[cle] = point
    return [
        {"date": cle, "solde": derniers[cle]["solde"]}
        for cle in sorted(derniers)
    ]


def construire_serie_totale(series: Dict[str, List[dict]]) -> List[dict]:
    """Solde cumulé de toutes les banques, jour par jour.

    Chaque banque n'entre dans le total qu'à partir de sa propre date d'ancre :
    avant cette date son solde n'est pas connu, l'additionner reviendrait à
    inventer une valeur. Le total peut donc progresser d'un cran le jour où une
    banque devient connue — c'est la réalité, pas un artefact.

    Le dernier point égale la somme des soldes du reporting : il suffit que les
    séries d'entrée proviennent de `construire_serie_soldes`.
    """
    if not series:
        return []

    # Valeur de chaque banque indexée par date + sa première date connue.
    par_banque = {}
    for code, points in series.items():
        valeurs = {p["date"]: p["solde"] for p in points}
        if not valeurs:
            continue
        par_banque[code] = (valeurs, min(valeurs))

    toutes_les_dates = sorted({
        date_point
        for valeurs, _debut in par_banque.values()
        for date_point in valeurs
    })

    # Report de la dernière valeur connue : une banque dont la série s'arrête
    # avant une date (borne « Au » propre à son relevé) garde son dernier solde
    # dans le total, au lieu de disparaître et de faire chuter la courbe. Une
    # banque n'entre dans le total qu'à partir de sa première date connue.
    total = []
    derniere_valeur = {}
    for date_point in toutes_les_dates:
        for code, (valeurs, debut) in par_banque.items():
            if date_point in valeurs:
                derniere_valeur[code] = valeurs[date_point]
        if derniere_valeur:
            total.append({
                "date": date_point,
                "solde": round(sum(derniere_valeur.values()), 3),
            })
    return total


# ─── Déduplication des mouvements (imports incrémentaux) ───

def empreinte_mouvement(compte_banque, mouvement: dict) -> tuple:
    """Clé d'identité d'un mouvement bancaire, stable d'un relevé à l'autre.

    Un relevé de fin de journée répète les opérations du matin et y ajoute les
    nouvelles : c'est la référence de l'opération (TT…, FT…) accompagnée de sa
    date et de ses montants qui l'identifie, jamais la période du relevé.
    La clé ne dépend pas du fichier importé, ce qui permet de reconnaître un
    mouvement déjà en base quel que soit le PDF qui le contient.
    """
    date_operation = mouvement.get("date_operation")
    date_texte = date_operation.isoformat() if hasattr(date_operation, "isoformat") else str(date_operation or "")
    return (
        (compte_banque or "").strip().upper(),
        date_texte,
        (mouvement.get("reference") or "").strip().upper(),
        round(_montant(mouvement.get("debit")), 3),
        round(_montant(mouvement.get("credit")), 3),
    )


def separer_mouvements_nouveaux(mouvements: List[dict], deja_importes) -> dict:
    """Sépare les mouvements inédits de ceux déjà présents en base.

    `deja_importes` est un itérable d'empreintes (voir `empreinte_mouvement`).
    Un mouvement déjà connu est ignoré sans être modifié : son classement en
    base (nature, auteur) doit survivre à un nouvel import du même relevé.

    Une même empreinte peut apparaître deux fois dans un relevé (deux virements
    réellement identiques le même jour). Le compteur d'occurrences évite alors
    de supprimer la seconde : seul ce qui dépasse le nombre déjà en base est
    considéré comme nouveau.
    """
    restants: Dict[tuple, int] = {}
    for empreinte in deja_importes or ():
        restants[empreinte] = restants.get(empreinte, 0) + 1

    nouveaux, ignores = [], []
    for mouvement in mouvements:
        empreinte = empreinte_mouvement(mouvement.get("compte_banque"), mouvement)
        if restants.get(empreinte):
            restants[empreinte] -= 1
            ignores.append(mouvement)
        else:
            nouveaux.append(mouvement)
    return {"nouveaux": nouveaux, "ignores": ignores}
