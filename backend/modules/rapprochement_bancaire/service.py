import io
import re
import unicodedata
import pandas as pd
import pdfplumber
from datetime import date, datetime, timedelta
from typing import List
from fastapi import HTTPException
from difflib import SequenceMatcher

from modules.rapprochement_bancaire.models import (
    BankMovement,
    SageMovement,
    ReconciledPair,
    DiscrepancyPair,
    ReconciliationStats,
    ReconciliationResult,
    ReconciliationOptions,
    OpeningBalanceInfo,
)

# Import the parsing helpers from saisie_bancaire service
from modules.saisie_bancaire.service import (
    _parse_csv_text,
    _parse_pdf,
    _extract_movements,
    _find_single_amount,
    _map_columns,
    _parse_amount,
    _parse_date
)


SAGE_OPENING_LABELS = ("solde initial", "cumul avant", "solde ouverture", "report a nouveau")
BANK_OPENING_LABELS = (
    "solde depart",
    "solde de depart",
    "solde debut de periode",
    "opening balance",
)

FRENCH_DATE_PATTERN = re.compile(
    r"\b\d{1,2}\s+(?:janvier|janv|fevrier|fevr|mars|avril|avr|mai|juin|"
    r"juillet|juil|aout|septembre|sept|octobre|oct|novembre|nov|decembre|dec)"
    r"\.?\s+\d{2,4}\b",
    re.IGNORECASE,
)
NUMERIC_DATE_PATTERN = re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")
MONEY_PATTERN = re.compile(
    r"[-+]?(?:\d{1,3}(?:[ ,.\u00a0\u202f]\d{3})+|\d+)(?:[,.]\d{2,3})"
)


def _normalize_text(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _read_sage_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    extension = filename.split(".")[-1].lower()
    if extension in {"xlsx", "xls"}:
        # Conserver les dates Excel comme objets date/heure. Une conversion forcée
        # en texte transformait par exemple 2026-05-01 en 2026-01-05 avec dayfirst.
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=object)
    elif extension in {"csv", "txt"}:
        try:
            content = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode("latin-1")
            except UnicodeDecodeError:
                content = file_bytes.decode("utf-8", errors="ignore")
        non_empty_lines = [line for line in content.splitlines() if line.strip()][:20]
        semi_count = sum(line.count(";") for line in non_empty_lines)
        comma_count = sum(line.count(",") for line in non_empty_lines)
        df = pd.read_csv(io.StringIO(content), sep=";" if semi_count > comma_count else ",", dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Format de fichier Sage non supporté")

    df.columns = [str(col).strip() for col in df.columns]
    normalized_columns = [_normalize_text(col).replace(" ", "") for col in df.columns]
    has_headers = (
        any("compte" in col or "code" in col for col in normalized_columns)
        and any("date" in col for col in normalized_columns)
        and any("deb" in col or "cre" in col for col in normalized_columns)
    )
    if not has_headers:
        for idx in range(min(100, len(df))):
            values = [_normalize_text(value).replace(" ", "") for value in df.iloc[idx] if not pd.isna(value)]
            if (
                any("compte" in value or "code" in value for value in values)
                and any("date" in value for value in values)
                and any("deb" in value or "cre" in value for value in values)
            ):
                new_columns = [str(value).strip() for value in df.iloc[idx]]
                df = df.iloc[idx + 1:].copy()
                df.columns = new_columns
                break
    return df


def _map_sage_columns(df: pd.DataFrame) -> dict:
    mapping = {}
    for col in df.columns:
        normalized = _normalize_text(col).replace(" ", "")
        if "codecompte" in normalized or ("compte" in normalized and "code" in normalized):
            mapping["code_compte"] = col
        elif "compte" in normalized and ("libel" in normalized or "nom" in normalized):
            mapping["libelle_compte"] = col
        elif "date" in normalized:
            mapping["date_ecriture"] = col
        elif "journal" in normalized or "jnl" in normalized:
            mapping["journal"] = col
        elif "piece" in normalized or "num" in normalized:
            mapping["numero_piece"] = col
        elif "libel" in normalized:
            mapping["libelle_ecriture"] = col
        elif "ref" in normalized:
            mapping["reference_piece"] = col
        elif "deb" in normalized:
            mapping["debit"] = col
        elif "cre" in normalized:
            mapping["credit"] = col
        elif normalized == "solde" or "balance" in normalized:
            mapping["balance"] = col

    fallbacks = {"code_compte": 0, "date_ecriture": 2, "debit": 9, "credit": 10}
    for required, index in fallbacks.items():
        if required not in mapping and len(df.columns) > index:
            mapping[required] = df.columns[index]
    for required in ("code_compte", "date_ecriture", "debit", "credit"):
        if required not in mapping:
            raise HTTPException(status_code=400, detail=f"Colonne requise '{required}' manquante dans le fichier Sage.")
    return mapping


def _read_bank_dataframe(file_bytes: bytes, filename: str, file_type: str) -> pd.DataFrame:
    extension = filename.split(".")[-1].lower()
    if extension in {"xlsx", "xls"}:
        return pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    if extension in {"csv", "txt"}:
        return _parse_csv_text(file_bytes.decode("utf-8", errors="ignore"))
    if extension == "pdf" or "pdf" in file_type:
        return _parse_pdf(file_bytes)
    raise HTTPException(status_code=400, detail="Format de relevé bancaire non supporté")


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
    df = _read_sage_dataframe(file_bytes, filename)
    col_mapping = _map_sage_columns(df)

    movements = []
    for _, row in df.iterrows():
        # Ignorer les lignes de totaux ou de report à nouveau cumulé si elles ne contiennent pas de code compte valide
        code = str(row.get(col_mapping.get("code_compte")) or "").strip()
        if not code or code.lower() == "nan" or "total" in code.lower():
            continue

        source_label = str(row.get(col_mapping.get("libelle_ecriture")) or "").strip()
        if any(pattern in _normalize_text(source_label) for pattern in SAGE_OPENING_LABELS):
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
    df = _read_bank_dataframe(file_bytes, filename, file_type)
    extracted = _extract_movements(df)
    
    movements = []
    for m in extracted:
        if any(pattern in _normalize_text(m.get("libelle")) for pattern in BANK_OPENING_LABELS):
            continue
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


def _matching_opening_label(row, preferred_columns, patterns):
    for column in preferred_columns:
        if column is None:
            continue
        value = row.get(column)
        normalized = _normalize_text(value)
        if any(pattern in normalized for pattern in patterns):
            return str(value).replace("\n", " ").strip()
    for value in row.values:
        normalized = _normalize_text(value)
        if any(pattern in normalized for pattern in patterns):
            return str(value).replace("\n", " ").strip()
    return None


def extract_sage_opening_balance(
    file_bytes: bytes,
    filename: str,
) -> OpeningBalanceInfo:
    """Extrait la ligne « Cumul avant » sans l'ajouter aux mouvements rapprochables."""
    df = _read_sage_dataframe(file_bytes, filename)
    mapping = _map_sage_columns(df)
    candidates = []
    for _, row in df.iterrows():
        label = _matching_opening_label(
            row,
            [mapping.get("libelle_ecriture"), mapping.get("libelle_compte")],
            SAGE_OPENING_LABELS,
        )
        if not label:
            continue
        balance_column = mapping.get("balance")
        balance_value = row.get(balance_column) if balance_column else None
        has_balance = balance_value is not None and not pd.isna(balance_value) and str(balance_value).strip() != ""
        if has_balance:
            amount = _parse_amount(balance_value)
        else:
            debit = _parse_amount(row.get(mapping.get("debit")))
            credit = _parse_amount(row.get(mapping.get("credit")))
            amount = debit - credit
        candidates.append(OpeningBalanceInfo(
            amount=round(amount, 3),
            label=label,
            balance_date=_parse_date(row.get(mapping.get("date_ecriture"))),
        ))
    return candidates[-1] if candidates else OpeningBalanceInfo()


def _extract_opening_amount_from_line(line: str) -> float:
    """Isole le montant final sans concaténer l'année courte qui le précède."""
    without_dates = FRENCH_DATE_PATTERN.sub(" ", line)
    without_dates = NUMERIC_DATE_PATTERN.sub(" ", without_dates)
    amounts = MONEY_PATTERN.findall(without_dates)
    return _parse_amount(amounts[-1]) if amounts else 0.0


def _extract_opening_date_from_line(line: str):
    numeric_match = NUMERIC_DATE_PATTERN.search(line)
    if numeric_match:
        return _parse_date(numeric_match.group(0))
    french_match = FRENCH_DATE_PATTERN.search(_normalize_text(line))
    return _parse_date(french_match.group(0)) if french_match else None


def _extract_biat_positioned_opening(pdf) -> OpeningBalanceInfo:
    """Détermine le signe du solde BIAT depuis sa colonne visuelle Débit/Crédit."""
    for page in pdf.pages:
        words = page.extract_words() or []
        debit_headers = []
        credit_headers = []
        for word in words:
            compact = _normalize_text(word.get("text")).replace(" ", "")
            center = (float(word["x0"]) + float(word["x1"])) / 2
            if compact in {"debit", "dbit"}:
                debit_headers.append((float(word["top"]), center))
            elif compact in {"credit", "crdit"}:
                credit_headers.append((float(word["top"]), center))

        for anchor in words:
            if _normalize_text(anchor.get("text")) != "solde":
                continue
            line_words = sorted(
                (word for word in words if abs(float(word["top"]) - float(anchor["top"])) <= 1.5),
                key=lambda word: float(word["x0"]),
            )
            line = " ".join(str(word.get("text") or "") for word in line_words)
            normalized = _normalize_text(line)
            if not any(pattern in normalized for pattern in BANK_OPENING_LABELS):
                continue
            amount = _extract_opening_amount_from_line(line)
            if amount == 0 or len(line_words) < 2:
                continue

            gaps = [
                float(line_words[index]["x0"]) - float(line_words[index - 1]["x1"])
                for index in range(1, len(line_words))
            ]
            amount_start = gaps.index(max(gaps)) + 1
            amount_words = line_words[amount_start:]
            amount_center = (
                float(amount_words[0]["x0"]) + float(amount_words[-1]["x1"])
            ) / 2
            line_top = float(anchor["top"])
            debit_candidates = [item for item in debit_headers if item[0] < line_top]
            credit_candidates = [item for item in credit_headers if item[0] < line_top]
            debit_center = min(debit_candidates, key=lambda item: line_top - item[0])[1] if debit_candidates else None
            credit_center = min(credit_candidates, key=lambda item: line_top - item[0])[1] if credit_candidates else None
            if debit_center is not None and (
                credit_center is None or abs(amount_center - debit_center) <= abs(amount_center - credit_center)
            ):
                amount = -abs(amount)
            elif credit_center is not None:
                amount = abs(amount)
            return OpeningBalanceInfo(
                amount=round(amount, 3),
                label=line.strip(),
                balance_date=_extract_opening_date_from_line(line),
            )
    return OpeningBalanceInfo()


def extract_bank_opening_balance(
    file_bytes: bytes,
    filename: str,
    file_type: str,
) -> OpeningBalanceInfo:
    """Extrait le solde de départ bancaire avant le parseur partagé de Saisie Bancaire."""
    is_pdf = filename.split(".")[-1].lower() == "pdf" or "pdf" in file_type
    try:
        df = _read_bank_dataframe(file_bytes, filename, file_type)
    except HTTPException:
        if not is_pdf:
            raise
        df = pd.DataFrame()
    mapping = _map_columns(df)
    candidates = []
    for _, row in df.iterrows():
        label = _matching_opening_label(row, [mapping.get("libelle")], BANK_OPENING_LABELS)
        if not label:
            continue
        debit = _parse_amount(row.get(mapping.get("debit")))
        credit = _parse_amount(row.get(mapping.get("credit")))
        amount = credit - debit
        if amount == 0:
            excluded = {
                mapping.get("date_operation"), mapping.get("date_valeur"),
                mapping.get("libelle"), mapping.get("reference"),
                mapping.get("debit"), mapping.get("credit"),
            }
            amount = _find_single_amount(row, {column for column in excluded if column})
        if amount == 0:
            continue
        candidates.append(OpeningBalanceInfo(
            amount=round(amount, 3),
            label=label,
            balance_date=_parse_date(row.get(mapping.get("date_operation"))),
        ))
    if candidates:
        return candidates[-1]

    if is_pdf:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pdf_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            if "biat" in _normalize_text(pdf_text):
                positioned = _extract_biat_positioned_opening(pdf)
                if positioned.amount is not None:
                    return positioned
            for page in pdf.pages:
                for line in (page.extract_text() or "").splitlines():
                    normalized = _normalize_text(line)
                    if not any(pattern in normalized for pattern in BANK_OPENING_LABELS):
                        continue
                    amount = _extract_opening_amount_from_line(line)
                    if amount == 0:
                        continue
                    return OpeningBalanceInfo(
                        amount=round(amount, 3),
                        label=line.strip(),
                        balance_date=_extract_opening_date_from_line(line),
                    )
    return OpeningBalanceInfo()


def calculate_reconciliation_balances(
    result: ReconciliationResult,
    sage_opening: float | None,
    bank_opening: float | None,
) -> dict:
    """Calcule les deux soldes ajustés selon le principe de rapprochement bancaire.

    Les mouvements présents uniquement en banque corrigent le solde comptable.
    Les écritures présentes uniquement dans SAGE corrigent le solde bancaire.
    """
    stats = result.stats
    sage_closing = None
    bank_closing = None
    if sage_opening is not None:
        sage_closing = sage_opening + stats.sage_total_debit - stats.sage_total_credit
    if bank_opening is not None:
        bank_closing = bank_opening + stats.bank_total_credit - stats.bank_total_debit

    adjusted_sage = None if sage_closing is None else (
        sage_closing + sum(item.amount for item in result.bank_only)
    )
    adjusted_bank = None if bank_closing is None else (
        bank_closing + sum(item.amount for item in result.sage_only)
    )
    residual = None
    if adjusted_sage is not None and adjusted_bank is not None:
        residual = adjusted_sage - adjusted_bank

    if residual is None:
        status = "unverifiable"
    elif abs(residual) <= 0.01 and not result.discrepancies:
        status = "balanced"
    else:
        status = "difference"

    return {
        "sage_closing_balance": round(sage_closing, 3) if sage_closing is not None else None,
        "bank_closing_balance": round(bank_closing, 3) if bank_closing is not None else None,
        "adjusted_sage_balance": round(adjusted_sage, 3) if adjusted_sage is not None else None,
        "adjusted_bank_balance": round(adjusted_bank, 3) if adjusted_bank is not None else None,
        "residual_difference": round(residual, 3) if residual is not None else None,
        "reconciliation_status": status,
    }


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
