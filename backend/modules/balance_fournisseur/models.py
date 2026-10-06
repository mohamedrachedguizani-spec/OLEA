from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class LigneTransaction(BaseModel):
    date: str
    libelle: str
    compte: str = ""           # 401 dettes / 408 factures non parvenues / 409 avances versées
    debit: float = 0.0
    credit: float = 0.0
    solde: float = 0.0         # 401/408 : montant dû (+) ; 409 : avance versée (+)
    reste_du: float = 0.0      # 401 : reste à payer (sens D) ou reste à imputer (sens C)
    jours_retard: int = 0      # jours depuis la date de la pièce
    sens: str = ""             # "D" = dette ouverte, "C" = paiement/avoir non imputé
    bucket: str = ""


class FournisseurBalance(BaseModel):
    code: str
    nom: str
    total_solde: float = 0.0           # solde dû compte 401 (+ = nous devons, – = paiements en excès)
    non_echu: float = 0.0
    echu_30: float = 0.0
    echu_60: float = 0.0
    echu_90: float = 0.0
    echu_plus: float = 0.0
    credit_non_affecte: float = 0.0    # 401 : paiements / avoirs non imputés (fournisseur nous doit)
    avance_buckets: Dict[str, float] = {}   # idem, ventilé par ancienneté
    dont_report: float = 0.0           # part des dettes issue du report à nouveau (âge inconnu)
    fnp: float = 0.0                   # 408 factures non parvenues (dû)
    avance_409: float = 0.0            # 409 avances et acomptes versés
    lignes: List[LigneTransaction] = []


class BalanceFournisseurResponse(BaseModel):
    date_reference: str
    delai_paiement: int = 0
    total_general: float               # net 401 (dettes – paiements non imputés)
    total_dettes: float = 0.0
    total_non_imputes: float = 0.0     # ≤ 0
    total_fnp: float = 0.0
    total_avances: float = 0.0         # 409
    total_net: float = 0.0             # 401 + 408 – 409 (= – total général Sage)
    total_report: float = 0.0
    totaux_buckets: Dict[str, float] = {}
    totaux_avances: Dict[str, float] = {}
    nb_fournisseurs: int
    fournisseurs: List[FournisseurBalance]
    controle: Dict[str, Any] = {}
    rapport_id: Optional[int] = None      # id dans l'historique (balance_agee_reports)
    fichier: Optional[str] = None
    genere_le: Optional[str] = None
    genere_par: Optional[str] = None
    avertissements: List[str] = []


class BalanceExportFournisseurs(BaseModel):
    analyse: BalanceFournisseurResponse
    fichier: Optional[str] = None
    inclure_detail: bool = True