from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional, Dict, Any


class ExtractionControl(BaseModel):
    statut: str = "OK"
    fichier: Optional[str] = None
    format_detecte: Optional[str] = None
    lignes_source: int = 0
    lignes_extraites: int = 0
    lignes_ignorees: int = 0
    total_debit: float = 0.0
    total_credit: float = 0.0
    solde_initial: Optional[float] = None
    solde_final: Optional[float] = None
    solde_final_calcule: Optional[float] = None
    ecart: Optional[float] = None
    messages: List[str] = Field(default_factory=list)
    details: List[Dict[str, Any]] = Field(default_factory=list)


class BankReconciliationBatchBase(BaseModel):
    periode_debut: Optional[date] = None
    periode_fin: Optional[date] = None
    compte_banque: str
    compte_comptable: str
    file_name: str
    file_type: str
    taux_conversion: Optional[float] = None
    devise_source: Optional[str] = None


class BankReconciliationBatch(BankReconciliationBatchBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BankReconciliationMovement(BaseModel):
    id: int
    batch_id: int
    date_operation: date
    reference: Optional[str] = None
    libelle: str
    debit: float
    credit: float
    created_at: datetime

    class Config:
        from_attributes = True


class BankReconciliationUploadResponse(BaseModel):
    batch: BankReconciliationBatch
    total_mouvements: int
    preview: List[BankReconciliationMovement]
    controle_extraction: Optional[ExtractionControl] = None


class BankReconciliationSageGenerationRequest(BaseModel):
    contrepartie_compte: Optional[str] = None
    contreparties: Optional[Dict[int, str]] = None
    tiers: Optional[str] = None
    section_analytique: Optional[str] = None
    tiers_by_movement: Optional[Dict[int, str]] = None
    sections_by_movement: Optional[Dict[int, str]] = None


class BankReconciliationSageLine(BaseModel):
    movement_id: int
    line_no: int
    societe: str
    journal: str
    date_ecriture: date
    compte: Optional[str] = None
    tiers: Optional[str] = None
    debit: float = 0
    credit: float = 0
    section_analytique: Optional[str] = None
    numero_piece: str
    libelle: str
    devise: str
    type_piece: str


class BankReconciliationSageLinesResponse(BaseModel):
    batch_id: int
    lines: List[BankReconciliationSageLine]


class BankReconciliationSageSaveResponse(BaseModel):
    batch_id: int
    saved_count: int


# ===================== Session de saisie =====================

class SessionEntryValue(BaseModel):
    compte: Optional[str] = None
    tiers: Optional[str] = None
    section_analytique: Optional[str] = None


class SaveSessionRequest(BaseModel):
    entries: Dict[int, SessionEntryValue]


class SessionEntry(BaseModel):
    movement_id: int
    compte: Optional[str] = None
    tiers: Optional[str] = None
    section_analytique: Optional[str] = None

    class Config:
        from_attributes = True


class SaveSessionResponse(BaseModel):
    batch_id: int
    saved_count: int


class PendingSession(BaseModel):
    id: int
    compte_banque: str
    compte_comptable: str
    file_name: str
    status: str
    created_at: datetime
    taux_conversion: Optional[float] = None
    devise_source: Optional[str] = None
    created_by_user_id: Optional[int] = None       
    created_by_username: Optional[str] = None       
    total_movements: int
    completed_movements: int

    class Config:
        from_attributes = True
