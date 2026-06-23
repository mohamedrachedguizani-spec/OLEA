# modules/saisie_caisse/models.py
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


# ─── Écritures de caisse ───

class EcritureCaisseBase(BaseModel):
    date_ecriture: date
    libelle_ecriture: str
    debit: float = 0
    credit: float = 0
    compte_contrepartie: Optional[str] = None
    tiers: Optional[str] = None
    section_analytique: Optional[str] = None


class EcritureCaisseCreate(EcritureCaisseBase):
    pass


class EcritureCaisse(EcritureCaisseBase):
    id: int
    solde: float
    est_migree: bool
    created_at: datetime

    class Config:
        from_attributes = True


class EcritureCaissePage(BaseModel):
    items: List[EcritureCaisse]
    total: int
    page: int
    page_size: int
    pages: int


# ─── Suggestions de libellés ───

class LibelleSuggestion(BaseModel):
    libelle: str
    compte_suggestion: Optional[str] = None
    tiers_suggestion: Optional[str] = None
    section_analytique_suggestion: Optional[str] = None
