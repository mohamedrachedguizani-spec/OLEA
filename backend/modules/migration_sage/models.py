# modules/migration_sage/models.py
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


# ─── Écritures Sage ───

class EcritureSageBase(BaseModel):
    date_compta: date
    compte: str
    tiers: Optional[str] = None
    section_analytique: Optional[str] = None
    libelle_ecriture: str
    numero_piece: str


class EcritureSageCreate(EcritureSageBase):
    ecriture_caisse_id: int
    montant_debit: float = 0
    montant_credit: float = 0
    societe: str = "TN01"
    journal: str = "CAI"
    devise: str = "TND"
    type_piece: str = "OD"


class EcritureSage(EcritureSageCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Migration ───

class MigrationRequest(BaseModel):
    ecriture_caisse_id: int
    ligne1: EcritureSageBase
    ligne2: EcritureSageBase
