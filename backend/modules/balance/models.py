from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class LigneTransaction(BaseModel):
    date: str
    libelle: str
    debit: float = 0.0
    credit: float = 0.0
    solde: float = 0.0
    reste_du: float = 0.0      # part de cette écriture encore impayée (après lettrage FIFO)
    jours_retard: int = 0
    sens: str = ""             # "D" = créance, "C" = crédit (reste_du = reste à affecter)
    bucket: str = ""           # "" si l'écriture est soldée / n'est pas une créance


class ClientBalance(BaseModel):
    code: str
    nom: str
    total_solde: float = 0.0   # solde Sage (positif = client débiteur, négatif = avance / avoir)
    non_echu: float = 0.0
    echu_30: float = 0.0
    echu_60: float = 0.0
    echu_90: float = 0.0
    echu_plus: float = 0.0
    credit_non_affecte: float = 0.0   # paiements en excès (avance client)
    dont_report: float = 0.0          # part des créances issue du report à nouveau (âge inconnu)
    avance_buckets: Dict[str, float] = {}   # avances ventilées par ancienneté (depuis l'encaissement)
    lignes: List[LigneTransaction] = []


class BalanceAgeeResponse(BaseModel):
    date_reference: str
    delai_paiement: int = 0
    total_general: float                 # solde net (débiteurs - créditeurs)
    total_debiteur: float = 0.0
    total_crediteur: float = 0.0
    total_report: float = 0.0
    totaux_buckets: Dict[str, float] = {}
    totaux_avances: Dict[str, float] = {}
    nb_clients: int
    clients: List[ClientBalance]
    controle: Dict[str, Any] = {}
    rapport_id: Optional[int] = None      # id dans l'historique (balance_agee_reports)
    fichier: Optional[str] = None
    genere_le: Optional[str] = None
    genere_par: Optional[str] = None
    avertissements: List[str] = []

class BalanceExportClients(BaseModel):
    """Corps des routes /agee/export-pdf et /agee/print-html : l'analyse déjà calculée est réutilisée."""
    analyse: BalanceAgeeResponse
    fichier: Optional[str] = None
    inclure_detail: bool = True