import pandas as pd
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from .models import LigneComptableSage, LigneBudgetBFC, TableauBFCResponse, TableauBFCSummary
from .mapper import SageBFCMapper

class SageBalanceParser:
    """
    Parser des balances SAGE avec mapping automatique BFC
    """
    
    def __init__(self, mapper: SageBFCMapper):
        self.mapper = mapper
    
    def parse_file(self, file_content: bytes, filename: str, 
                   periode: date = None) -> TableauBFCResponse:
        """
        Parse un fichier balance SAGE (Excel ou CSV).
        La période est obligatoire — pas de détection automatique.
        """
        if periode is None:
            raise ValueError("La période comptable est obligatoire. Veuillez la spécifier lors de l'upload.")
        
        # Détection format
        suffix = Path(filename).suffix.lower()
        
        if suffix in ['.xlsx', '.xls']:
            df = self._read_excel(file_content)
        elif suffix == '.csv':
            df = self._read_csv(file_content)
        else:
            raise ValueError(f"Format non supporté: {suffix}")
        
        # Parsing des lignes
        lignes_sage = self._parse_dataframe(df)
        
        # Mapping vers BFC
        lignes_bfc = []
        for ligne in lignes_sage:
            mapped = self.mapper.map_ligne(ligne, periode, filename)
            if mapped:
                lignes_bfc.append(mapped)
        
        # Calculs agrégats
        agregats = self.mapper.calculer_agregats(lignes_bfc)
        
        # Validations
        validations = self.mapper.executer_validations(lignes_bfc, agregats, periode)
        
        # Construction réponse
        resume = TableauBFCSummary(
            periode=periode,
            ca_brut=float(agregats['ca_brut']),
            retrocessions=float(agregats['retrocessions']),
            ca_net=float(agregats['ca_net']),
            autres_produits=float(agregats['autres_produits']),
            total_produits=float(agregats['total_produits']),
            frais_personnel=float(agregats['frais_personnel']),
            honoraires=float(agregats['honoraires']),
            frais_commerciaux=float(agregats['frais_commerciaux']),
            impots_taxes=float(agregats['impots_taxes']),
            fonctionnement=float(agregats['fonctionnement']),
            autres_charges=float(agregats['autres_charges']),
            total_charges=float(agregats['total_charges']),
            ebitda=float(agregats['ebitda']),
            ebitda_pct=float(agregats['ebitda_pct']),
            produits_financiers=float(agregats['produits_financiers']),
            charges_financieres=float(agregats['charges_financieres']),
            resultat_financier=float(agregats['resultat_financier']),
            dotations=float(agregats['dotations']),
            resultat_avant_impot=float(agregats['resultat_avant_impot']),
            impot_societes=float(agregats['impot_societes']),
            resultat_net=float(agregats['resultat_net']),
            resultat_net_pct=float(agregats['resultat_net_pct'])
        )
        
        return TableauBFCResponse(
            periode=periode,
            lignes=lignes_bfc,
            resume=resume,
            validations=validations,
            alertes_globales=[]
        )
    
    def _read_excel(self, content: bytes) -> pd.DataFrame:
        """Lit un fichier Excel depuis des bytes"""
        return pd.read_excel(io.BytesIO(content))
    
    def _read_csv(self, content: bytes) -> pd.DataFrame:
        """Lit un fichier CSV avec détection automatique"""
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        delimiters = [';', ',', '\t']
        
        for encoding in encodings:
            for delimiter in delimiters:
                try:
                    df = pd.read_csv(
                        io.BytesIO(content), 
                        encoding=encoding, 
                        delimiter=delimiter
                    )
                    return df
                except:
                    continue
        
        raise ValueError("Impossible de lire le CSV - encodage ou délimiteur non reconnu")
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Détecte automatiquement les colonnes"""
        cols = {str(c).lower().strip(): c for c in df.columns}
        detected = {}
        
        # Code compte
        patterns_code = ['compte', 'code', 'n° compte', 'numéro', 'numero', 'account']
        for pattern in patterns_code:
            for col_lower, col_orig in cols.items():
                if pattern in col_lower:
                    detected['code'] = col_orig
                    break
            if 'code' in detected:
                break
        
        # Libellé
        patterns_lib = ['libellé', 'intitulé', 'nom', 'description', 'libelle', 'intitule']
        for pattern in patterns_lib:
            for col_lower, col_orig in cols.items():
                if pattern in col_lower:
                    detected['libelle'] = col_orig
                    break
            if 'libelle' in detected:
                break
        
        # Montant/Solde
        patterns_montant = ['solde', 'balance', 'montant', 'total', 'amount', 'value']
        for pattern in patterns_montant:
            for col_lower, col_orig in cols.items():
                if pattern in col_lower:
                    detected['montant'] = col_orig
                    break
            if 'montant' in detected:
                break
        
        # Débit/Crédit optionnels
        for col_lower, col_orig in cols.items():
            if any(x in col_lower for x in ['débit', 'debit']):
                detected['debit'] = col_orig
            if any(x in col_lower for x in ['crédit', 'credit']):
                detected['credit'] = col_orig
        
        return detected
    
    def _parse_dataframe(self, df: pd.DataFrame) -> List[LigneComptableSage]:
        """Parse le DataFrame en objets LigneComptableSage"""
        columns = self._detect_columns(df)
        
        if 'code' not in columns or 'montant' not in columns:
            raise ValueError(f"Colonnes essentielles non détectées. Colonnes trouvées: {list(df.columns)}")
        
        lignes = []
        
        for idx, row in df.iterrows():
            try:
                code = str(row[columns['code']]).strip()
                
                # Filtres
                if pd.isna(code) or code in ['', 'nan', 'None', 'Total', 'TOTAL']:
                    continue
                
                if not self._is_valid_code_compte(code):
                    continue
                
                libelle = str(row.get(columns.get('libelle', ''), '')).strip()
                if libelle in ['nan', 'None']:
                    libelle = ''
                
                # Montants
                montant = self._parse_montant(row[columns['montant']])
                debit = Decimal('0')
                credit = Decimal('0')
                
                if 'debit' in columns:
                    debit = self._parse_montant(row.get(columns['debit'], 0))
                if 'credit' in columns:
                    credit = self._parse_montant(row.get(columns['credit'], 0))
                
                # Recalcule solde si débit/crédit présents
                if debit != 0 or credit != 0:
                    montant = credit - debit
                
                lignes.append(LigneComptableSage(
                    code_compte=code,
                    libelle=libelle,
                    solde=montant,
                    debit=debit,
                    credit=credit
                ))
                
            except Exception as e:
                continue
        
        return lignes
    
    def _is_valid_code_compte(self, code: str) -> bool:
        """Valide le format du code compte SAGE"""
        if not code:
            return False
        return bool(re.match(r'^\d{6,7}[A-Z]?$', str(code).strip()))
    
    def _parse_montant(self, valeur) -> Decimal:
        """Parse un montant avec nettoyage"""
        if pd.isna(valeur):
            return Decimal('0')
        
        if isinstance(valeur, (int, float)):
            return Decimal(str(valeur))
        
        val_str = str(valeur).strip()
        
        # Nettoyage
        val_str = val_str.replace(' ', '').replace(',', '.')
        
        # Parenthèses = négatif
        if val_str.startswith('(') and val_str.endswith(')'):
            val_str = '-' + val_str[1:-1]
        
        # Symboles monétaires
        for sym in ['TND', '€', '$', '£', 'DT']:
            val_str = val_str.replace(sym, '')
        
        try:
            return Decimal(val_str)
        except:
            return Decimal('0')
    
    def _extract_period_from_filename(self, filename: str) -> date:
        """Extrait la période du nom de fichier"""
        patterns = [
            (r'20(\d{2})[\-_]?(\d{2})', lambda m: (2000 + int(m.group(1)), int(m.group(2)))),
            (r'(\d{2})[\-_]?20(\d{2})', lambda m: (2000 + int(m.group(2)), int(m.group(1)))),
            (r'(\d{2})[\-_]?(\d{4})', lambda m: (int(m.group(2)), int(m.group(1)))),
        ]
        
        for pattern, extractor in patterns:
            match = re.search(pattern, filename)
            if match:
                year, month = extractor(match)
                try:
                    return date(year, month, 1)
                except:
                    continue
        
        return date.today().replace(day=1)