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
            brand_fees=float(agregats['brand_fees']),
            management_fees=float(agregats['management_fees']),
            interco_charges=float(agregats['interco_charges']),
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
            resume=resume
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
        
        # Code compte — priorité aux colonnes contenant "code" (exclure "libellé")
        for col_lower, col_orig in cols.items():
            if 'code' in col_lower and 'libellé' not in col_lower and 'libelle' not in col_lower:
                detected['code'] = col_orig
                break
        if 'code' not in detected:
            patterns_code = ['n° compte', 'numéro', 'numero', 'compte', 'account']
            for pattern in patterns_code:
                for col_lower, col_orig in cols.items():
                    if pattern in col_lower and 'libellé' not in col_lower and 'libelle' not in col_lower:
                        detected['code'] = col_orig
                        break
                if 'code' in detected:
                    break
        
        # Libellé — exclure la colonne déjà utilisée pour le code
        code_col_lower = str(detected.get('code', '')).lower().strip()
        patterns_lib = ['libellé', 'intitulé', 'nom', 'description', 'libelle', 'intitule']
        for pattern in patterns_lib:
            for col_lower, col_orig in cols.items():
                if pattern in col_lower and col_lower != code_col_lower:
                    detected['libelle'] = col_orig
                    break
            if 'libelle' in detected:
                break
        
        # ── Débit / Crédit (priorité aux colonnes "cumulé") ──
        debit_candidates = []
        credit_candidates = []
        for col_lower, col_orig in cols.items():
            if any(x in col_lower for x in ['débit', 'debit']):
                debit_candidates.append((col_lower, col_orig))
            if any(x in col_lower for x in ['crédit', 'credit']):
                credit_candidates.append((col_lower, col_orig))
        
        # Privilégier "cumulé", sinon "période", sinon le premier trouvé
        def _pick_best(candidates, priority_keywords=('cumulé', 'cumule', 'cumul')):
            for kw in priority_keywords:
                for cl, co in candidates:
                    if kw in cl:
                        return co
            return candidates[0][1] if candidates else None
        
        best_debit = _pick_best(debit_candidates)
        best_credit = _pick_best(credit_candidates)
        if best_debit:
            detected['debit'] = best_debit
        if best_credit:
            detected['credit'] = best_credit
        
        # ── Montant / Solde (optionnel si débit+crédit trouvés) ──
        patterns_montant = ['solde', 'balance', 'montant', 'total', 'amount', 'value']
        for pattern in patterns_montant:
            for col_lower, col_orig in cols.items():
                if pattern in col_lower:
                    detected['montant'] = col_orig
                    break
            if 'montant' in detected:
                break
        
        return detected
    
    def _parse_dataframe(self, df: pd.DataFrame) -> List[LigneComptableSage]:
        """Parse le DataFrame en objets LigneComptableSage"""
        columns = self._detect_columns(df)
        
        has_montant = 'montant' in columns
        has_debit_credit = 'debit' in columns and 'credit' in columns
        
        if 'code' not in columns or (not has_montant and not has_debit_credit):
            raise ValueError(
                f"Colonnes essentielles non détectées. "
                f"Il faut au minimum 'Code compte' + ('Solde/Montant' OU 'Débit'+'Crédit'). "
                f"Colonnes trouvées: {list(df.columns)}"
            )
        
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
                debit = Decimal('0')
                credit = Decimal('0')
                montant = Decimal('0')
                
                if has_debit_credit:
                    debit = self._parse_montant(row.get(columns['debit'], 0))
                    credit = self._parse_montant(row.get(columns['credit'], 0))
                    montant = credit - debit
                elif has_montant:
                    montant = self._parse_montant(row[columns['montant']])
                
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
        """Valide le format du code compte SAGE (5 à 7 chiffres + suffixe optionnel)"""
        if not code:
            return False
        return bool(re.match(r'^\d{5,7}[A-Z]?$', str(code).strip()))
    
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