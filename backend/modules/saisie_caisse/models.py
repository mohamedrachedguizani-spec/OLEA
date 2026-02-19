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


class EcritureCaisseCreate(EcritureCaisseBase):
    pass


class EcritureCaisse(EcritureCaisseBase):
    id: int
    solde: float
    est_migree: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Suggestions de libellés ───

class LibelleSuggestion(BaseModel):
    libelle: str
    compte_suggestion: Optional[str] = None
    tiers_suggestion: Optional[str] = None
    section_analytique_suggestion: Optional[str] = None
