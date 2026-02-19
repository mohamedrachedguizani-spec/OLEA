from decimal import Decimal
from typing import Dict, Any, List
from datetime import date
import re

from .models import LigneComptableSage, LigneBudgetBFC, ValidationResult

class SageBFCMapper:
    """
    Mapper intelligent des balances SAGE vers format BFC
    """
    
    def __init__(self, mapping_config: Dict[str, Any]):
        self.mapping = mapping_config
        self.flat_mapping = {}
        self._build_flat_mapping()
        
    def _build_flat_mapping(self):
        """Aplatit le mapping hiérarchique"""
        categories_mapping = [
            'mapping_chiffre_affaires',
            'mapping_retrocessions',
            'mapping_frais_personnel',
            'mapping_interco_frais',
            'mapping_honoraires',
            'mapping_frais_commerciaux',
            'mapping_impots',
            'mapping_fonctionnement',
            'mapping_autres_charges',
            'mapping_produits_exploitation',
            'mapping_produits_financiers',
            'mapping_charges_financieres',
            'mapping_dotations',
            'mapping_produits_exceptionnels',
            'mapping_charges_exceptionnelles',
            'mapping_impots_societes',
            'mapping_capex'
        ]
        
        for category in categories_mapping:
            if category in self.mapping:
                for code, config in self.mapping[category].items():
                    if isinstance(config, dict) and 'agregat_bfc' in config:
                        self.flat_mapping[code] = config.copy()
                        self.flat_mapping[code]['categorie_source'] = category
    
    def map_ligne(self, ligne_sage: LigneComptableSage, periode: date, source: str) -> LigneBudgetBFC:
        """Mappe une ligne SAGE vers BFC"""
        config = self.flat_mapping.get(ligne_sage.code_compte)
        
        if not config:
            return None
        
        # Ajustement montant selon sens
        montant = ligne_sage.solde
        if config['sens'] == '-' and montant > 0:
            montant = -montant
        elif config['sens'] == '+' and montant < 0:
            montant = abs(montant)
        
        # Alertes spécifiques
        alertes = []
        if config.get('validation_interco'):
            alertes.append(f"Validation interco requise: {config['validation_interco'].get('type', 'N/A')}")
        
        return LigneBudgetBFC(
            code_sage=ligne_sage.code_compte,
            libelle_sage=ligne_sage.libelle or config.get('libelle_sage', ''),
            agregat_bfc=config['agregat_bfc'],
            categorie=config['categorie'],
            type_ligne=config['type'],
            sens=config['sens'],
            montant=montant,
            montant_absolu=abs(montant),
            sous_categorie=config.get('sous_categorie'),
            is_principal=config.get('is_principal', False),
            bpc_mapping=config.get('bpc_mapping'),
            bfc_mapping=config.get('bfc_mapping'),
            validation_interco=config.get('validation_interco'),
            alertes=alertes,
            periode=periode,
            source_fichier=source
        )
    
    def calculer_agregats(self, lignes: List[LigneBudgetBFC]) -> Dict[str, Decimal]:
        """Calcule tous les agrégats du P&L.
        
        Convention: le mapper applique sens +/- sur les montants (charges deviennent négatives).
        Ici on utilise abs() pour récupérer les valeurs absolues des charges,
        puis on applique les formules standard du P&L avec soustraction.
        Les produits restent positifs naturellement.
        """
        
        def sum_by_agregat(nom: str) -> Decimal:
            return sum((l.montant for l in lignes if l.agregat_bfc == nom), Decimal('0'))
        
        # Produits (positifs naturellement)
        ca_brut = sum_by_agregat('CA Brut')
        autres_produits = sum_by_agregat('Autres Produits d\'Exploitation')
        produits_financiers = sum_by_agregat('Produits Financiers')
        produits_except = sum_by_agregat('Produits Exceptionnels')
        
        # Charges: abs() car le mapper les a déjà négativées via sens="-"
        retrocessions = abs(sum_by_agregat('Retrocessions'))
        frais_personnel = abs(sum_by_agregat('Frais de Personnel'))
        honoraires = abs(sum_by_agregat('Honoraires & Sous-traitance'))
        frais_commerciaux = abs(sum_by_agregat('Frais Commerciaux'))
        impots_taxes = abs(sum_by_agregat('Impôts et taxes'))
        fonctionnement = abs(sum_by_agregat('Fonctionnement Courant'))
        autres_charges = abs(sum_by_agregat('Autres Charges'))
        charges_financieres = abs(sum_by_agregat('Charges Financières'))
        dotations = abs(sum_by_agregat('Dotations Amortissements & Provisions'))
        charges_except = abs(sum_by_agregat('Charges Exceptionnelles'))
        impot_societes = abs(sum_by_agregat('Impôt sur les sociétés'))
        
        # Calculs P&L
        ca_net = ca_brut - retrocessions
        total_produits = ca_net + autres_produits
        
        total_charges = frais_personnel + honoraires + frais_commerciaux + impots_taxes + fonctionnement + autres_charges
        
        ebitda = total_produits - total_charges
        ebitda_pct = (ebitda / ca_net * 100) if ca_net else Decimal('0')
        
        resultat_financier = produits_financiers - charges_financieres
        resultat_except = produits_except - charges_except
        
        resultat_avant_impot = ebitda + resultat_financier - dotations + resultat_except
        resultat_net = resultat_avant_impot - impot_societes
        resultat_net_pct = (resultat_net / ca_net * 100) if ca_net else Decimal('0')
        
        return {
            'ca_brut': ca_brut,
            'retrocessions': retrocessions,
            'ca_net': ca_net,
            'autres_produits': autres_produits,
            'total_produits': total_produits,
            'frais_personnel': frais_personnel,
            'honoraires': honoraires,
            'frais_commerciaux': frais_commerciaux,
            'impots_taxes': impots_taxes,
            'fonctionnement': fonctionnement,
            'autres_charges': autres_charges,
            'total_charges': total_charges,
            'ebitda': ebitda,
            'ebitda_pct': ebitda_pct,
            'produits_financiers': produits_financiers,
            'charges_financieres': charges_financieres,
            'resultat_financier': resultat_financier,
            'dotations': dotations,
            'resultat_avant_impot': resultat_avant_impot,
            'impot_societes': impot_societes,
            'resultat_net': resultat_net,
            'resultat_net_pct': resultat_net_pct
        }
    
    def executer_validations(self, lignes: List[LigneBudgetBFC], 
                           agregats: Dict[str, Decimal], 
                           periode: date) -> List[ValidationResult]:
        """Exécute les validations interco"""
        validations = []
        validations_config = self.mapping.get('validations_interco', {})
        
        # Validation IT Costs (3%)
        if validations_config.get('it_costs', {}).get('actif'):
            it_montant = sum(
                l.montant_absolu for l in lignes 
                if l.sous_categorie == 'IT Costs'
            )
            ca = agregats['ca_brut']
            attendu = ca * Decimal('0.03')
            ecart = abs(it_montant - attendu)
            tolerance = validations_config['it_costs'].get('tolerance_absolue', 500)
            
            validations.append(ValidationResult(
                nom='IT Costs vs CA (3%)',
                montant_reel=float(it_montant),
                montant_attendu=float(attendu),
                ecart=float(ecart),
                statut='OK' if ecart <= tolerance else 'ALERTE',
                description=f'IT Costs: {it_montant:,.2f} vs Attendu: {attendu:,.2f} (3% du CA)'
            ))
        
        # Validation Brand Fees (0.83% sur T4)
        if validations_config.get('brand_fees', {}).get('actif') and periode.month >= 10:
            brand_montant = sum(
                l.montant_absolu for l in lignes 
                if l.sous_categorie == 'Frais de marque' or 'brand' in l.libelle_sage.lower()
            )
            ca_trimestre = agregats['ca_brut']
            attendu = ca_trimestre * Decimal('0.0083')
            
            validations.append(ValidationResult(
                nom='Brand Fees T4 (0.83%)',
                montant_reel=float(brand_montant),
                montant_attendu=float(attendu),
                ecart=float(abs(brand_montant - attendu)),
                statut='INFO',
                description='Validation T4 uniquement - 0.83% du CA'
            ))
        
        return validations
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du mapping"""
        categories = {}
        for v in self.flat_mapping.values():
            cat = v.get('categorie', 'N/A')
            categories[cat] = categories.get(cat, 0) + 1
        
        validations_actives = [
            k for k, v in self.mapping.get('validations_interco', {}).items() 
            if v.get('actif')
        ]
        
        return {
            'version': self.mapping.get('version', 'unknown'),
            'description': self.mapping.get('description', ''),
            'total_codes_mappes': len(self.flat_mapping),
            'categories': list(categories.keys()),
            'codes_par_categorie': categories,
            'validations_actives': validations_actives
        }