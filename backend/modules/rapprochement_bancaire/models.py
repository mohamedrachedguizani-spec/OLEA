from pydantic import BaseModel
from datetime import date
from typing import List, Optional

class ReconciliationOptions(BaseModel):
    date_tolerance_days: int = 3
    match_on_label: bool = False
    match_on_date: bool = False

class BankMovement(BaseModel):
    date_operation: date
    reference: Optional[str] = None
    libelle: str
    debit: float
    credit: float
    amount: float

class SageMovement(BaseModel):
    code_compte: str
    libelle_compte: str
    date_ecriture: date
    journal: str
    numero_piece: str
    libelle_ecriture: str
    reference_piece: Optional[str] = None
    debit: float
    credit: float
    amount: float

class ReconciledPair(BaseModel):
    bank: BankMovement
    sage: SageMovement
    match_type: str  # "perfect" or "amount_only"
    confidence: float  # e.g., 100.0 or 70.0

class DiscrepancyPair(BaseModel):
    bank: BankMovement
    sage: SageMovement
    difference: float

class ReconciliationStats(BaseModel):
    total_bank_movements: int
    total_sage_movements: int
    auto_reconciled_count: int
    manual_validation_count: int
    discrepancies_count: int
    total_discrepancy_amount: float
    automation_rate: float
    bank_total_debit: float = 0.0
    bank_total_credit: float = 0.0
    sage_total_debit: float = 0.0
    sage_total_credit: float = 0.0

class ReconciliationResult(BaseModel):
    stats: ReconciliationStats
    reconciled: List[ReconciledPair]
    bank_only: List[BankMovement]
    sage_only: List[SageMovement]
    discrepancies: List[DiscrepancyPair]


class ReconciliationPdfRequest(BaseModel):
    result: ReconciliationResult
    sage_filename: Optional[str] = None
    bank_filename: Optional[str] = None
