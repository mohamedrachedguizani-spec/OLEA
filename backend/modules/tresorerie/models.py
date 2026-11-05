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

    non_classe_count: int = 0
    non_classe_debit: float = 0
    non_classe_credit: float = 0
    total_debit: float = 0
    total_credit: float = 0
    nb_mouvements: int = 0


class TresorerieReportingResponse(BaseModel):
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    banques: List[TresorerieBanqueReporting] = Field(default_factory=list)
    totaux: TresorerieBanqueReporting
    controle: dict = Field(default_factory=dict)
