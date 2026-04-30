from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

# Modèles de données pour l'API

class LigneComptableSage(BaseModel):
    """Ligne brute issue de SAGE"""
    code_compte: str
    libelle: str
    solde: Decimal
    debit: Decimal = Decimal('0')
    credit: Decimal = Decimal('0')
    numero_piece: Optional[str] = None
    date_piece: Optional[date] = None
    journal: Optional[str] = None

class LigneBudgetBFC(BaseModel):
    """Ligne transformée au format Budget BFC"""
    code_sage: str
    libelle_sage: str
    agregat_bfc: str
    categorie: str
    type_ligne: str  # Produit ou Charge
    sens: str  # + ou -
    montant: Decimal
    montant_absolu: Decimal
    sous_categorie: Optional[str] = None
    is_principal: bool = False
    bpc_mapping: Optional[str] = None
    bfc_mapping: Optional[str] = None
    validation_interco: Optional[Dict] = None
    periode: Optional[date] = None
    source_fichier: Optional[str] = None

class TableauBFCSummary(BaseModel):
    """Résumé du tableau BFC"""
    periode: date
    ca_brut: float
    retrocessions: float
    ca_net: float
    autres_produits: float
    total_produits: float
    frais_personnel: float
    honoraires: float
    frais_commerciaux: float
    impots_taxes: float
    fonctionnement: float
    autres_charges: float
    brand_fees: float = 0.0
    management_fees: float = 0.0
    interco_charges: float = 0.0
    total_charges: float
    ebitda: float
    ebitda_pct: float
    produits_financiers: float
    charges_financieres: float
    resultat_financier: float
    dotations: float
    produits_exceptionnels: float = 0.0
    charges_exceptionnelles: float = 0.0
    resultat_exceptionnel: float = 0.0
    resultat_avant_impot: float
    impot_societes: float
    resultat_net: float
    resultat_net_pct: float

class TableauBFCResponse(BaseModel):
    """Réponse complète du tableau BFC"""
    periode: date
    lignes: List[LigneBudgetBFC]
    resume: TableauBFCSummary

class ParseRequest(BaseModel):
    """Requête de parsing"""
    periode: date

class MonthlyDataSummary(BaseModel):
    """Résumé d'un mois stocké (sans lignes, pour la liste)"""
    periode: date
    file_name: Optional[str] = None
    lignes_count: int = 0
    resume: TableauBFCSummary
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class MonthlyDataFull(BaseModel):
    """Données complètes d'un mois stocké"""
    periode: date
    file_name: Optional[str] = None
    lignes_count: int = 0
    resume: TableauBFCSummary
    lignes: List[LigneBudgetBFC] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ExportExcelRequest(BaseModel):
    """Requête d'export Excel"""
    tableau_id: str  # Identifiant unique du tableau généré

class MappingStats(BaseModel):
    """Statistiques du mapping"""
    version: str
    description: str
    total_codes_mappes: int
    categories: List[str]
    codes_par_categorie: Dict[str, int]
    validations_actives: List[str]

class MappingEntryBase(BaseModel):
    code_compte: str = Field(..., description="Code compte SAGE")
    libelle_sage: str = Field(..., description="Libellé SAGE")
    categorie: str = Field(..., description="Catégorie métier")
    type_ligne: str = Field(..., alias="type", description="Type: Produit ou Charge")
    agregat_bfc: str = Field(..., description="Agrégat BFC")
    sens: str = Field(..., description="Sens + ou -")

    sous_categorie: Optional[str] = None
    is_principal: Optional[bool] = None
    bpc_mapping: Optional[str] = None
    bfc_mapping: Optional[str] = None
    validation_interco: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    mapping_section: Optional[str] = Field(default=None, alias="mapping_section")

    class Config:
        validate_by_name = True

class MappingEntryResponse(MappingEntryBase):
    mapping_section: str = Field(..., alias="mapping_section")

    class Config:
        validate_by_name = True

class MappingConfigResponse(BaseModel):
    version: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    regles_agregation: Optional[Dict[str, Any]] = None
    validations_interco: Optional[Dict[str, Any]] = None
    alertes_metier: Optional[Dict[str, Any]] = None
    correspondances_bpc_bfc: Optional[Dict[str, Any]] = None
    mapping: Dict[str, Dict[str, Any]]