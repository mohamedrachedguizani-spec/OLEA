# modules/tresorerie/constants.py
"""Référentiel du module Trésorerie : banques et natures de mouvement."""

# Banques reprises à l'identique de la saisie bancaire / du rapprochement,
# afin qu'un même relevé puisse être exploité dans les deux modules.
BANQUES_TRESORERIE = {
    "BI1 TRAPSA": {"libelle": "BIAT – compte 1", "compte_comptable": "5320000T"},
    "BI2 649 ": {"libelle": "BIAT – compte 2", "compte_comptable": "5320003T"},
    "BI3 643": {"libelle": "BIAT – compte 3", "compte_comptable": "5320002T"},
    "TN-ATB1": {"libelle": "ATB – compte 1", "compte_comptable": "5320001T"},
    "UB1": {"libelle": "UBCI – compte 1", "compte_comptable": "5320007T"},
    "UB2": {"libelle": "UBCI – compte EUR", "compte_comptable": "5320009T"},
    "UB3": {"libelle": "UBCI – compte USD", "compte_comptable": "5320008T"},
}

# Devises des comptes qui ne sont pas en dinars : un taux de conversion est exigé.
DEVISES_TRESORERIE = {"UB2": "EUR", "UB3": "USD"}

# Natures de mouvement utilisées pour le reporting.
NATURE_EXPLOITATION = "exploitation"
NATURE_HORS_EXPLOITATION = "hors_exploitation"
NATURE_COMMISSION = "commission"

NATURES_TRESORERIE = (
    NATURE_EXPLOITATION,
    NATURE_HORS_EXPLOITATION,
    NATURE_COMMISSION,
)

NATURE_LABELS = {
    NATURE_EXPLOITATION: "Exploitation",
    NATURE_HORS_EXPLOITATION: "Hors exploitation",
    NATURE_COMMISSION: "Commission",
}


def normaliser_nature(nature) -> "str | None":
    """Retourne une nature valide, ou None si absente. Lève ValueError sinon."""
    if nature is None:
        return None
    valeur = str(nature).strip().lower()
    if valeur == "":
        return None
    if valeur not in NATURES_TRESORERIE:
        raise ValueError(
            "Nature invalide : valeurs attendues "
            + ", ".join(NATURES_TRESORERIE)
        )
    return valeur


# ─── Règles de suggestion automatique ───
# Ce sont des propositions pré-cochées, jamais un classement imposé :
# l'utilisateur reste maître de la nature de chaque mouvement.

_COMMISSION_PATTERNS = (
    "commission",
    "comm sur",
    "com virement",
    "comm virement",
    "frais",
    "frais bancaire",
    "tenue de compte",
    "recherche de documents",
    "acheminement",
    "agios",
    "tva sur",
)

_HORS_EXPLOITATION_PATTERNS = (
    "interet",
    "interets",
    "dividende",
    "cession",
    "plus-value",
    "moins-value",
    "impot",
    "is ",
    "tcl",
    "taxe",
    "amende",
    "penalite",
    "emprunt",
    "echeance pret",
    "remboursement pret",
    "rachat",
    "souscription titre",
    "placement",
    "virement interne",
    "transfert interne",
    "apport en capital",
    "dotation",
)


def suggerer_nature(libelle, debit: float, credit: float) -> "str | None":
    """Suggestion de nature à partir du libellé (comparaison normalisée).

    Les commissions sont proposées en priorité (souvent incluses dans le
    débit d'exploitation), puis les opérations typiquement hors exploitation.
    """
    import unicodedata

    brut = (libelle or "").lower()
    texte = "".join(
        ch for ch in unicodedata.normalize("NFKD", brut) if not unicodedata.combining(ch)
    )
    texte = " " + " ".join(texte.split()) + " "

    for motif in _COMMISSION_PATTERNS:
        if motif in texte:
            return NATURE_COMMISSION
    for motif in _HORS_EXPLOITATION_PATTERNS:
        if motif in texte:
            return NATURE_HORS_EXPLOITATION
    return NATURE_EXPLOITATION
