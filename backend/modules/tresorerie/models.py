# modules/tresorerie/models.py
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional


# ─── Référentiel des banques ───

class BanqueTresorerie(BaseModel):
    code: str
    libelle: str
    compte_comptable: Optional[str] = None


# ─── Imports d'extraits bancaires ───

class TresorerieImport(BaseModel):
    id: int
    compte_banque: str
    periode_debut: Optional[date] = None
    periode_fin: Optional[date] = None
    file_name: str
    file_type: str
    taux_conversion: Optional[float] = None
    devise_source: Optional[str] = None
    solde_ouverture: Optional[float] = None
    solde_ouverture_date: Optional[date] = None
    total_mouvements: int = 0
    total_debit: float = 0
    total_credit: float = 0
    created_by_user_id: Optional[int] = None
    created_by_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TresorerieMovement(BaseModel):
    id: int
    import_id: int
    date_operation: date
    reference: Optional[str] = None
    libelle: str
    debit: float = 0
    credit: float = 0
    nature: Optional[str] = None
    nature_suggeree: Optional[str] = None
    classified_by_username: Optional[str] = None
    classified_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TresorerieMovementListItem(TresorerieMovement):
    """Mouvement affiché avec la banque de son import."""
    compte_banque: str


class TresorerieMovementPage(BaseModel):
    items: List[TresorerieMovementListItem]
    total: int
    page: int
    page_size: int
    pages: int
    compteurs: dict = Field(default_factory=dict)


class TresorerieImportResponse(BaseModel):
    """Réponse d'un import : entête, aperçu et contrôle d'extraction."""
    import_batch: TresorerieImport
    total_mouvements: int
    preview: List[TresorerieMovement]
    controle_extraction: Optional[dict] = None
    # Solde de départ à valider/corriger dans la modale de contrôle d'extraction.
    solde_ouverture_fige: bool = False
    solde_ouverture_lu: Optional[float] = None
    solde_ouverture_date_lue: Optional[date] = None
    solde_ouverture_actuel: Optional[float] = None
    solde_ouverture_date_actuelle: Optional[date] = None
    a_un_solde: bool = False


# ─── Classement des mouvements ───

class NatureUpdateRequest(BaseModel):
    nature: Optional[str] = Field(
        default=None,
        description="exploitation | hors_exploitation | commission | null",
    )


class BulkNatureUpdateRequest(BaseModel):
    movement_ids: List[int] = Field(default_factory=list)
    nature: Optional[str] = Field(
        default=None,
        description="exploitation | hors_exploitation | commission | null",
    )


class NatureUpdateResponse(BaseModel):
    updated: int
    nature: Optional[str] = None


# ─── Solde de départ (ancre par banque) ───

class SoldeOuvertureRequest(BaseModel):
    solde: float
    date_solde: date


class SoldeOuverture(BaseModel):
    compte_banque: str
    solde: float
    date_solde: date
    source_file_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Reporting ───

class TresorerieBanqueReporting(BaseModel):
    compte_banque: str
    libelle_banque: Optional[str] = None

    recette_exploitation: float = 0
    dont_recette_commission: float = 0
    depense_exploitation: float = 0
    dont_depense_commission: float = 0
    tresorerie_nette_exploitation: float = 0

    recette_hors_exploitation: float = 0
    depense_hors_exploitation: float = 0
    tresorerie_nette_hors_exploitation: float = 0

    # Net des deux blocs additionnés : recettes totales moins dépenses totales.
    tresorerie_nette_globale: float = 0

    non_classe_count: int = 0
    non_classe_debit: float = 0
    non_classe_credit: float = 0
    total_debit: float = 0
    total_credit: float = 0
    nb_mouvements: int = 0

    # Solde du compte : ancre figée sur le premier relevé + mouvements.
    solde: Optional[float] = None
    solde_ouverture: Optional[float] = None
    solde_ouverture_date: Optional[date] = None


class TresorerieCommissionsBanque(BaseModel):
    compte_banque: str
    libelle_banque: Optional[str] = None
    commissions_encaissees: float = 0
    commissions_payees: float = 0
    total_commissions: float = 0
    commissions_nettes: float = 0
    nb_mouvements: int = 0


class TresorerieCommissions(BaseModel):
    par_banque: List[TresorerieCommissionsBanque] = Field(default_factory=list)
    total_encaissees: float = 0
    total_payees: float = 0
    total_commissions: float = 0
    total_nettes: float = 0


class TresorerieReportingResponse(BaseModel):
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    # Date à laquelle les soldes sont arrêtés : borne « Au » si saisie, sinon
    # dernière date de mouvement importée. None si le rapport est vide.
    date_arret: Optional[date] = None
    banques: List[TresorerieBanqueReporting] = Field(default_factory=list)
    totaux: TresorerieBanqueReporting
    commissions: TresorerieCommissions = Field(default_factory=TresorerieCommissions)
    controle: dict = Field(default_factory=dict)
