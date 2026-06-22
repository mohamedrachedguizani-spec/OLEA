import io
import re
import pandas as pd
from datetime import date, datetime, timedelta
from typing import List, Dict, Tuple, Optional
from fastapi import HTTPException
from difflib import SequenceMatcher

from modules.rapprochement_bancaire.models import (
    BankMovement,
    SageMovement,
    ReconciledPair,
    DiscrepancyPair,
    ReconciliationStats,
    ReconciliationResult,
    ReconciliationOptions
)

# Import the parsing helpers from saisie_bancaire service
from modules.saisie_bancaire.service import (
    _parse_csv_text,
    _parse_pdf,
    _extract_movements,
    _parse_amount,
    _parse_date
)


def normalize_libelle(libelle: str) -> str:
    """Normalise un libellé pour faciliter la comparaison (minuscules, sans caractères spéciaux)."""
    if not libelle:
        return ""
    # Convertir en minuscules
    normalized = libelle.lower()
    # Supprimer les accents simples ou remplacer par équivalents de base
    # Remplacer les caractères non alphanumériques par des espaces
    normalized = re.sub(r"[^a-z0-9]", " ", normalized)
    # Remplacer les espaces multiples par un seul espace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def get_similarity_ratio(a: str, b: str) -> float:
    """Calcule le taux de similarité entre deux chaînes (entre 0.0 et 1.0)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def parse_sage_file(file_bytes: bytes, filename: str) -> List[SageMovement]:
    """Parse un fichier Grand Livre Sage (CSV ou Excel) et retourne une liste de SageMovement."""
    extension = filename.split(".")[-1].lower()
    if extension in {"xlsx", "xls"}:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    elif extension in {"csv", "txt"}:
        # Tente de décoder avec différents encodages (latin-1 gère bien les accents français)
        try:
            content = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode("latin-1")
            except UnicodeDecodeError:
                content = file_bytes.decode("utf-8", errors="ignore")
        
        # Détection robuste du délimiteur (compte les points-virgules vs virgules sur les 20 premières lignes non vides)
        non_empty_lines = [line for line in content.splitlines() if line.strip()][:20]
        semi_count = sum(line.count(";") for line in non_empty_lines)
        comma_count = sum(line.count(",") for line in non_empty_lines)
        sep = ";" if semi_count > comma_count else ","
        df = pd.read_csv(io.StringIO(content), sep=sep, dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Format de fichier Sage non supporté")

    # Nettoyer les en-têtes de colonnes
    df.columns = [str(col).strip() for col in df.columns]

    # Essayer de trouver la ligne d'en-tête réelle de manière robuste
    # Étape 1 : Vérifier si les colonnes actuelles contiennent déjà les en-têtes requis
    cols_normalized = [str(c).lower().replace("é", "e").replace("è", "e").replace(" ", "") for c in df.columns]
    cols_normalized = [re.sub(r"[^a-z0-9]", "", c) for c in cols_normalized]
    
    has_compte = any("compte" in c or "code" in c for c in cols_normalized)
    has_date = any("date" in c for c in cols_normalized)
    has_debit_or_credit = any("deb" in c or "cre" in c or "dbit" in c or "crdit" in c for c in cols_normalized)
    
    # Si les colonnes actuelles ne sont pas les en-têtes, on scanne les lignes
    if not (has_compte and has_date and has_debit_or_credit):
        header_row_idx = None
        for idx in range(min(100, len(df))):
            row_vals = [str(val).strip().lower().replace("é", "e").replace("è", "e").replace(" ", "") for val in df.iloc[idx] if not pd.isna(val)]
            row_vals_norm = [re.sub(r"[^a-z0-9]", "", v) for v in row_vals]
            
            h_compte = any("compte" in v or "code" in v for v in row_vals_norm)
            h_date = any("date" in v for v in row_vals_norm)
            h_debit_or_credit = any("deb" in v or "cre" in v or "dbit" in v or "crdit" in v for v in row_vals_norm)
            
            if h_compte and h_date and h_debit_or_credit:
                header_row_idx = idx
                break
                
        if header_row_idx is not None:
            new_cols = [str(val).strip() for val in df.iloc[header_row_idx]]
            df = df.iloc[header_row_idx + 1:].copy()
            df.columns = [str(col).strip() for col in new_cols]

    # Mappage des colonnes (robuste face aux corruptions d'encodage et accents)
    col_mapping = {}
    for col in df.columns:
        normalized = col.lower().replace("é", "e").replace("è", "e").replace(" ", "")
        # Supprimer les caractères non-alphanumériques potentiellement corrompus
        normalized = re.sub(r"[^a-z0-9]", "", normalized)
        
        if "codecompte" in normalized or ("compte" in normalized and "code" in normalized):
            col_mapping["code_compte"] = col
        elif "compte" in normalized and ("libel" in normalized or "nom" in normalized):
            col_mapping["libelle_compte"] = col
        elif "date" in normalized:
            col_mapping["date_ecriture"] = col
        elif "journal" in normalized or "jnl" in normalized:
            col_mapping["journal"] = col
        elif "piece" in normalized or "num" in normalized:
            col_mapping["numero_piece"] = col
        elif "libel" in normalized:
            col_mapping["libelle_ecriture"] = col
        elif "ref" in normalized:
            col_mapping["reference_piece"] = col
        elif "deb" in normalized or "dbit" in normalized:
            col_mapping["debit"] = col
        elif "cre" in normalized or "crdit" in normalized:
            col_mapping["credit"] = col

    # Validation
    for req in ["code_compte", "date_ecriture", "debit", "credit"]:
        if req not in col_mapping:
            # Fallbacks manuels si non trouvés par heuristique
            if req == "code_compte" and len(df.columns) > 0: col_mapping["code_compte"] = df.columns[0]
            elif req == "date_ecriture" and len(df.columns) > 2: col_mapping["date_ecriture"] = df.columns[2]
            elif req == "debit" and len(df.columns) > 9: col_mapping["debit"] = df.columns[9]
            elif req == "credit" and len(df.columns) > 10: col_mapping["credit"] = df.columns[10]
            
            # Si toujours manquant après fallback
            if req not in col_mapping:
                raise HTTPException(status_code=400, detail=f"Colonne requise '{req}' manquante dans le fichier Sage.")

    movements = []
    for _, row in df.iterrows():
        # Ignorer les lignes de totaux ou de report à nouveau cumulé si elles ne contiennent pas de code compte valide
        code = str(row.get(col_mapping.get("code_compte")) or "").strip()
        if not code or code.lower() == "nan" or "total" in code.lower():
            continue

        date_val = _parse_date(row.get(col_mapping.get("date_ecriture")))
        if not date_val:
            continue

        debit = _parse_amount(row.get(col_mapping.get("debit")))
        credit = _parse_amount(row.get(col_mapping.get("credit")))

        # Ignorer les lignes vides
        if debit == 0 and credit == 0:
            continue

        # Ignorer les lignes qui contiennent à la fois du débit et du crédit (ex: cumuls/soldes de report)
        if debit > 0 and credit > 0:
            continue

        lib_compte = str(row.get(col_mapping.get("libelle_compte")) or "").strip()
        jnl = str(row.get(col_mapping.get("journal")) or "").strip() or "N/A"
        num_piece = str(row.get(col_mapping.get("numero_piece")) or "").strip() or "N/A"
        lib_ecriture = str(row.get(col_mapping.get("libelle_ecriture")) or "").strip() or "N/A"
        ref_piece = str(row.get(col_mapping.get("reference_piece")) or "").strip() or None

        # Montant directionnel : Débit = positif (+), Crédit = négatif (-) pour la banque
        amount = debit if debit > 0 else -credit

        movements.append(SageMovement(
            code_compte=code,
            libelle_compte=lib_compte,
            date_ecriture=date_val,
            journal=jnl,
            numero_piece=num_piece,
            libelle_ecriture=lib_ecriture,
            reference_piece=ref_piece,
            debit=debit,
            credit=credit,
            amount=amount
        ))

    return movements


def parse_bank_file(file_bytes: bytes, filename: str, file_type: str) -> List[BankMovement]:
    """Parse le relevé bancaire (PDF, Excel, CSV) et retourne une liste de BankMovement."""
    extension = filename.split(".")[-1].lower()
    
    if extension in {"xlsx", "xls"}:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    elif extension in {"csv", "txt"}:
        content = file_bytes.decode("utf-8", errors="ignore")
        df = _parse_csv_text(content)
    elif extension in {"pdf"} or "pdf" in file_type:
        df = _parse_pdf(file_bytes)
    else:
        raise HTTPException(status_code=400, detail="Format de relevé bancaire non supporté")

    extracted = _extract_movements(df)
    
    movements = []
    for m in extracted:
        # Montant directionnel pour le relevé bancaire :
        # Crédit (inflow) = positif (+), Débit (outflow) = négatif (-)
        # Ceci s'aligne avec Sage où Débit (compte 5) = augmentation (+), Crédit = diminution (-)
        amount = m["credit"] if m["credit"] > 0 else -m["debit"]
        
        movements.append(BankMovement(
            date_operation=m["date_operation"],
            reference=m["reference"],
            libelle=m["libelle"],
            debit=m["debit"],
            credit=m["credit"],
            amount=amount
        ))
        
    return movements


def reconcile(
    bank_list: List[BankMovement],
    sage_list: List[SageMovement],
    options: ReconciliationOptions
) -> ReconciliationResult:
    """
    Effectue la comparaison et le rapprochement entre le relevé bancaire et le grand livre Sage.
    Priorité absolue au montant, les autres champs (date, libellé) servent à calculer le taux de confiance.
    """
    reconciled: List[ReconciledPair] = []
    discrepancies: List[DiscrepancyPair] = []
    
    # Pools d'écritures non encore rapprochées
    remaining_bank = list(bank_list)
    remaining_sage = list(sage_list)

    # --- Étape 1 : Rapprochement basé sur le Montant d'abord ---
    bank_idx = 0
    while bank_idx < len(remaining_bank):
        bm = remaining_bank[bank_idx]
        found_match = False
        
        # Trouver tous les candidats Sage qui ont le même montant (à 0.01 près)
        candidates = []
        for sage_idx, sm in enumerate(remaining_sage):
            if abs(bm.amount - sm.amount) < 0.01:
                # Score de confiance de base (le montant correspond)
                score = 60.0
                
                # Date de l'écriture
                diff_days = abs((bm.date_operation - sm.date_ecriture).days)
                if diff_days == 0:
                    score += 25.0
                elif diff_days <= options.date_tolerance_days:
                    score += 15.0
                elif diff_days <= 7:
                    score += 5.0
                    
                # Comparaison de libellés via similarité (NLP léger)
                norm_b = normalize_libelle(bm.libelle)
                norm_s = normalize_libelle(sm.libelle_ecriture)
                similarity = get_similarity_ratio(norm_b, norm_s)
                
                if similarity >= 0.8:
                    score += 15.0
                elif similarity >= 0.5:
                    score += 10.0
                elif similarity >= 0.3:
                    score += 5.0
                    
                candidates.append((sage_idx, sm, score))
                
        if candidates:
            # Trier par score de confiance décroissant, puis par différence de date croissante
            candidates.sort(key=lambda x: (x[2], -abs((bm.date_operation - x[1].date_ecriture).days)), reverse=True)
            best_idx, best_sm, best_score = candidates[0]
            
            # Déterminer le type de match
            match_type = "perfect" if best_score >= 100.0 else "amount_only"
            
            reconciled.append(ReconciledPair(
                bank=bm,
                sage=best_sm,
                match_type=match_type,
                confidence=best_score
            ))
            
            remaining_bank.pop(bank_idx)
            remaining_sage.pop(best_idx)
            found_match = True
            
        if not found_match:
            bank_idx += 1

    # --- Étape 2 : Détection des Écarts de Montant sur les restes ---
    # Même date (dans la limite) et libellé similaire, mais montants différents
    bank_idx = 0
    while bank_idx < len(remaining_bank):
        bm = remaining_bank[bank_idx]
        found_match = False
        
        for sage_idx, sm in enumerate(remaining_sage):
            diff_days = abs((bm.date_operation - sm.date_ecriture).days)
            if diff_days <= options.date_tolerance_days:
                norm_b = normalize_libelle(bm.libelle)
                norm_s = normalize_libelle(sm.libelle_ecriture)
                
                # Détection des libellés à sens similaire (ex: seuil de 55% de ressemblance)
                if get_similarity_ratio(norm_b, norm_s) >= 0.55:
                    diff = abs(bm.amount - sm.amount)
                    discrepancies.append(DiscrepancyPair(
                        bank=bm,
                        sage=sm,
                        difference=diff
                    ))
                    remaining_bank.pop(bank_idx)
                    remaining_sage.pop(sage_idx)
                    found_match = True
                    break
                    
        if not found_match:
            bank_idx += 1

    # Métriques
    total_bank = len(bank_list)
    total_sage = len(sage_list)
    auto_reconciled = len(reconciled)
    discrepancies_count = len(discrepancies)
    total_discrepancy_amt = sum(d.difference for d in discrepancies)
    
    # Calcul des débits et crédits totaux
    sage_total_debit = sum(sm.debit for sm in sage_list)
    sage_total_credit = sum(sm.credit for sm in sage_list)
    bank_total_debit = sum(bm.debit for bm in bank_list)
    bank_total_credit = sum(bm.credit for bm in bank_list)

    # Reste
    bank_only = remaining_bank
    sage_only = remaining_sage
    
    # Taux d'automatisation
    automation_rate = (auto_reconciled / total_bank * 100) if total_bank > 0 else 0.0

    stats = ReconciliationStats(
        total_bank_movements=total_bank,
        total_sage_movements=total_sage,
        auto_reconciled_count=auto_reconciled,
        manual_validation_count=0,  # Peut être implémenté si besoin de confirmation manuelle
        discrepancies_count=discrepancies_count,
        total_discrepancy_amount=round(total_discrepancy_amt, 3),
        automation_rate=round(automation_rate, 2),
        bank_total_debit=round(bank_total_debit, 3),
        bank_total_credit=round(bank_total_credit, 3),
        sage_total_debit=round(sage_total_debit, 3),
        sage_total_credit=round(sage_total_credit, 3)
    )

    return ReconciliationResult(
        stats=stats,
        reconciled=reconciled,
        bank_only=bank_only,
        sage_only=sage_only,
        discrepancies=discrepancies
    )
