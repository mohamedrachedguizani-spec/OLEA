import io
import re
import unicodedata
from datetime import date, datetime
from typing import List, Optional
import pandas as pd
import pdfplumber
from dateutil import parser as date_parser
from fastapi import HTTPException

def _normalize_col(value: str) -> str:
    raw = (value or "").lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", raw)


def _looks_like_date_number(raw: str) -> bool:
    if not raw.isdigit() or len(raw) != 8:
        return False
    day = int(raw[0:2])
    month = int(raw[2:4])
    return 1 <= day <= 31 and 1 <= month <= 12


def _parse_amount(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        amount = float(value)
        if abs(amount) >= 1e9:
            return 0.0
        return amount
    raw = str(value).strip()
    if raw == "":
        return 0.0
    if re.match(r"^\d{2}[/-]\d{2}[/-]\d{4}$", raw):
        return 0.0
    raw = raw.replace(" ", "")
    raw = raw.replace("\u00a0", "")
    if re.search(r"[a-zA-Z]", raw):
        return 0.0
    if raw.isdigit() and len(raw) >= 12:
        return 0.0
    if _looks_like_date_number(raw):
        return 0.0

    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
        raw = re.sub(r"[^0-9.\-]", "", raw)
    elif "," in raw:
        raw = raw.replace(",", ".")
        raw = re.sub(r"[^0-9.\-]", "", raw)
    else:
        raw = re.sub(r"[^0-9.\-]", "", raw)

    if raw in {"", ".", "-", "-."}:
        return 0.0
    try:
        amount = float(raw)
        if abs(amount) >= 1e9:
            return 0.0
        return amount
    except ValueError:
        return 0.0


def _parse_date(value) -> Optional[date]:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date_parser.parse(str(value), dayfirst=True).date()
    except Exception:
        return None


def _find_header_index(lines: List[str]) -> Optional[int]:
    for idx, line in enumerate(lines):
        normalized = _normalize_col(line)
        has_date = "date" in normalized
        has_debit_credit = "debit" in normalized or "credit" in normalized
        has_desc = "description" in normalized or "libelle" in normalized
        has_operation = "operation" in normalized or "valeur" in normalized
        if has_date and has_debit_credit and (has_desc or has_operation):
            return idx
    return None


def _parse_csv_text(content: str) -> pd.DataFrame:
    lines = content.splitlines()
    header_idx = _find_header_index(lines)
    if header_idx is not None:
        content = "\n".join(lines[header_idx:])
    return pd.read_csv(io.StringIO(content), sep=";", dtype=str)


def _normalize_row_length(row: List, length: int) -> List:
    if len(row) == length:
        return row
    if len(row) > length:
        head = row[:length - 1]
        tail = row[length - 1:]
        merged = "".join(str(part or "").strip() for part in tail).strip()
        return head + [merged]
    return row + [None] * (length - len(row))


# =============================================================================
# PARSER PDF ATB TEXTE BRUT
# =============================================================================

def _is_atb_text_format(lines: list) -> bool:
    header_re = re.compile(
        r'Jour\s+D\.Valeur\s+Référence\s+Libellé\s+Mouvement\s+Débit\s+Crédit',
        re.IGNORECASE,
    )
    for line in lines:
        if header_re.search(line):
            return True
    return False


_DEBIT_PATTERNS = [
    re.compile(r'\bPAIEMENT\s+PAR\s+CARTE\b', re.IGNORECASE),
    re.compile(r'\bVIREMENT\s+EMIS\b', re.IGNORECASE),
    re.compile(r'\bCOMMISSION\b', re.IGNORECASE),
    re.compile(r'\bCOMM\s+SUR\b', re.IGNORECASE),
    re.compile(r'\bCOM\s+VIREMENT\b', re.IGNORECASE),
    re.compile(r'\bTVA\s+SUR\b', re.IGNORECASE),
    re.compile(r'\bRECHERCHE\s+DE\s+DOCUMENTS\b', re.IGNORECASE),
    re.compile(r'\bFRAIS\b', re.IGNORECASE),
    re.compile(r'\bREGLEMENT\b', re.IGNORECASE),
    re.compile(r'\bPAIEMENT\b', re.IGNORECASE),
]

_CREDIT_PATTERNS = [
    re.compile(r'\bVIREMENT\s+RECU\b', re.IGNORECASE),
    re.compile(r'\bVERSEMENT\s+ESPECE\b', re.IGNORECASE),
    re.compile(r'\bENCAISSEMENT\b', re.IGNORECASE),
    re.compile(r'\bTRANSFERT\s+-\s*RECU\b', re.IGNORECASE),
    re.compile(r'\bTRANSFERT\s+-RECU\b', re.IGNORECASE),
    re.compile(r'\bREMBOURSEMENT\b', re.IGNORECASE),
    re.compile(r'\bCREDIT\b', re.IGNORECASE),
]


def _classify_atb_movement(libelle: str) -> str:
    lu = libelle.upper()
    for pat in _DEBIT_PATTERNS:
        if pat.search(lu):
            return "debit"
    for pat in _CREDIT_PATTERNS:
        if pat.search(lu):
            return "credit"
    return "unknown"


def _parse_pdf_atb_text(file_bytes: bytes) -> pd.DataFrame:
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pt = page.extract_text()
            if pt:
                text += pt + "\n"

    if not text.strip():
        raise HTTPException(status_code=400, detail="PDF vide ou texte non extractible")

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if not _is_atb_text_format(lines):
        raise HTTPException(status_code=400, detail="Format ATB texte non reconnu")

    line_re = re.compile(r'^(\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$')
    ref_re = re.compile(r'^(FT|TT|CHG|ATB|TR)\w+$')

    skip_patterns = [
        re.compile(r'^Jour\s+D\.Valeur', re.IGNORECASE),
        re.compile(r'^Extrait\s+de\s+compte', re.IGNORECASE),
        re.compile(r'^Agence\s+\w+', re.IGNORECASE),
        re.compile(r'^Nom\s+client\s+', re.IGNORECASE),
        re.compile(r'^Compte\s+\d', re.IGNORECASE),
        re.compile(r'^Exgible', re.IGNORECASE),
        re.compile(r'^Date\s*:', re.IGNORECASE),
        re.compile(r'^Heure\s*:', re.IGNORECASE),
        re.compile(r'^Page\s*:', re.IGNORECASE),
        re.compile(r'^Compte\s*:\s*\d', re.IGNORECASE),
        re.compile(r'^Nom\s+Client\s*:', re.IGNORECASE),
    ]
    balance_re = re.compile(r'\b(?:Opening|Closing)\s+Balance\b', re.IGNORECASE)

    rows = []

    for line in lines:
        if any(p.match(line) for p in skip_patterns):
            continue
        if balance_re.search(line):
            continue

        m = line_re.match(line)
        if not m:
            continue

        jour = m.group(1)
        date_valeur = m.group(2)
        rest = m.group(3).strip()

        tokens = rest.split()

        ref = ""
        if tokens and ref_re.match(tokens[0]):
            ref = tokens[0]
            tokens = tokens[1:]

        if not tokens:
            continue

        amount_str = tokens[-1]
        amount = _parse_amount(amount_str)

        if amount == 0 and not re.match(r'^[\d\s\-\u2013\u2014,.]+$', amount_str):
            continue

        libelle = " ".join(tokens[:-1]) if len(tokens) > 1 else ""

        year = date_valeur.split("/")[-1]
        try:
            date_op = datetime.strptime(f"{jour}/{year}", "%d/%m/%Y").date()
        except ValueError:
            date_op = datetime.strptime(date_valeur, "%d/%m/%Y").date()
        date_val = datetime.strptime(date_valeur, "%d/%m/%Y").date()

        movement_type = _classify_atb_movement(libelle)
        debit = 0.0
        credit = 0.0

        if movement_type == "debit":
            debit = amount
        elif movement_type == "credit":
            credit = amount
        else:
            debit = amount

        rows.append({
            "date_operation": date_op,
            "date_valeur": date_val,
            "reference": ref,
            "libelle": libelle or "(sans libellé)",
            "debit": debit,
            "credit": credit,
        })

    if not rows:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le PDF ATB")

    return pd.DataFrame(rows)


# =============================================================================
# PARSER PDF BIAT TEXTE BRUT (avec bordures verticales pour Débit/Crédit)
# =============================================================================

def _is_biat_text_format(lines: list) -> bool:
    sample = " ".join(lines[:120]).upper()
    has_biat = "BIAT" in sample or "BANQUE INTERNATIONALE ARABE" in sample
    has_releve = (
        "RELEV" in sample
        or "COMPTE MENSUEL" in sample
        or "كشف" in sample
        or "كشفحساب" in sample
    )
    return has_biat and has_releve


def _parse_pdf_biat_text(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse BIAT en utilisant les bordures verticales du PDF pour déterminer
    exactement les colonnes Date, Libellé, Référence, Date valeur, Débit, Crédit.
    """
    from collections import defaultdict

    rows = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            vlines = [l for l in page.lines
                      if abs(l['x0'] - l['x1']) < 2 and l['bottom'] - l['top'] > 400]
            vlines = sorted(vlines, key=lambda l: l['x0'])
            x_borders = [l['x0'] for l in vlines]

            if len(x_borders) < 5:
                continue

            words = page.extract_words()
            table_words = [w for w in words if 240 < w['top'] < 720]

            lines = defaultdict(list)
            for w in table_words:
                y = round(w['top'])
                lines[y].append(w)

            blocks = []
            current_block = []

            for y in sorted(lines.keys()):
                line_words = lines[y]
                has_date_op = any(
                    w['x0'] < x_borders[0] and
                    re.match(r'^\d{2}/\d{2}/\d{4}$', w['text'].strip())
                    for w in line_words
                )

                if has_date_op and current_block:
                    blocks.append(current_block)
                    current_block = []

                current_block.extend(line_words)

            if current_block:
                blocks.append(current_block)

            for block in blocks:
                mov = {
                    'date_op': None,
                    'libelle': '',
                    'ref': '',
                    'date_val': None,
                    'debit': 0.0,
                    'credit': 0.0,
                }

                block_lines = defaultdict(list)
                for w in block:
                    y = round(w['top'])
                    block_lines[y].append(w)

                for y in sorted(block_lines.keys()):
                    line_words = block_lines[y]
                    line_by_col = defaultdict(list)

                    for w in line_words:
                        x = w['x0']
                        text = w['text'].strip()
                        col = None

                        if x < x_borders[0]:
                            col = 'date_op'
                        elif x_borders[0] <= x < x_borders[1]:
                            col = 'libelle'
                        elif x_borders[1] <= x < x_borders[2]:
                            col = 'ref'
                        elif x_borders[2] <= x < x_borders[3]:
                            col = 'date_val'
                        elif x_borders[3] <= x < x_borders[4]:
                            col = 'debit'
                        elif x >= x_borders[4]:
                            col = 'credit'

                        if col:
                            line_by_col[col].append(text)

                    for col, texts in line_by_col.items():
                        text = ' '.join(texts)

                        if col == 'date_op':
                            if re.match(r'^\d{2}/\d{2}/\d{4}$', text):
                                mov['date_op'] = text
                        elif col == 'libelle':
                            mov['libelle'] += (' ' if mov['libelle'] else '') + text
                        elif col == 'ref':
                            if re.match(r'^(FT|CHG|TT|PDL?)[A-Z0-9\\/_;.-]+$', text):
                                mov['ref'] = text
                        elif col == 'date_val':
                            if re.match(r'^\d{2}/\d{2}/\d{4}$', text):
                                mov['date_val'] = text
                        elif col == 'debit':
                            if re.match(r'^[0-9\s]{1,3}(?:\s[0-9]{3})*,\d{3}$|^\d{1,3},\d{3}$', text):
                                mov['debit'] = _parse_amount(text)
                        elif col == 'credit':
                            if re.match(r'^[0-9\s]{1,3}(?:\s[0-9]{3})*,\d{3}$|^\d{1,3},\d{3}$', text):
                                mov['credit'] = _parse_amount(text)

                if mov['date_op'] and mov['libelle'].strip():
                    libelle = mov['libelle'].strip()
                    skip = False
                    for kw in ['SOLDE AU', 'SOLDE', 'TOTAUX', 'TOTAL', 'الجملة', 'الرصيد', 'OPENING BALANCE', 'CLOSING BALANCE']:
                        if kw in libelle.upper():
                            skip = True
                            break
                    if not skip:
                        rows.append(mov)

    if not rows:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le PDF BIAT")

    df_rows = []
    for r in rows:
        date_op = _parse_date(r['date_op'])
        if not date_op:
            continue

        df_rows.append({
            'date_operation': date_op,
            'date_valeur': _parse_date(r['date_val']) if r['date_val'] else None,
            'reference': r['ref'] or None,
            'libelle': r['libelle'].strip(),
            'debit': r['debit'],
            'credit': r['credit'],
        })

    if not df_rows:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le PDF BIAT")

    return pd.DataFrame(df_rows)


# =============================================================================
# PARSER PDF GÉNÉRIQUE
# =============================================================================

def _parse_pdf(file_bytes: bytes) -> pd.DataFrame:
    raw_text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pt = page.extract_text()
            if pt:
                raw_text += pt + "\n"

    raw_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    if _is_biat_text_format(raw_lines):
        try:
            return _parse_pdf_biat_text(file_bytes)
        except HTTPException:
            pass

    if _is_atb_text_format(raw_lines):
        try:
            return _parse_pdf_atb_text(file_bytes)
        except HTTPException:
            pass

    rows = []
    header = None
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables or []:
                if not table:
                    continue
                for row in table:
                    if not row:
                        continue
                    if header is None:
                        normalized_row = [_normalize_col(c) for c in row if c]
                        joined = "".join(normalized_row)
                        has_date = "date" in joined
                        has_debit_credit = "debit" in joined or "credit" in joined
                        has_desc = "description" in joined or "libelle" in joined
                        has_operation = "operation" in joined or "valeur" in joined
                        if has_date and has_debit_credit and (has_desc or has_operation):
                            header = row
                            continue
                    if header is not None:
                        rows.append(_normalize_row_length(row, len(header)))

    if header is not None and rows:
        safe_rows = [
            _normalize_row_length(row, len(header))
            for row in rows
        ]
        df = pd.DataFrame(safe_rows, columns=header)
        if len(df) > 0:
            return df

    try:
        return _parse_pdf_atb_text(file_bytes)
    except HTTPException:
        pass

    try:
        return _parse_pdf_biat_text(file_bytes)
    except HTTPException:
        pass

    raise HTTPException(status_code=400, detail="En-tête introuvable dans le PDF")


def _map_columns(df: pd.DataFrame) -> dict:
    candidates = {
        "date_operation": {"dateoperation", "dateop", "date"},
        "date_valeur": {"datevaleur", "datevalue", "valeur"},
        "libelle": {"libelle", "libelleecriture", "libelleoperation", "libell", "description"},
        "debit": {"debit", "montantdebit"},
        "credit": {"credit", "montantcredit"},
        "reference": {"reference", "ref"},
    }

    mapping = {}
    for col in df.columns:
        norm = _normalize_col(str(col))
        for target, keys in candidates.items():
            if norm in keys or any(k in norm for k in keys):
                if target not in mapping:
                    mapping[target] = col
    return mapping


def _get_adjacent_amount(row: pd.Series, columns: List[str], col_name: str) -> float:
    if col_name not in columns:
        return 0.0
    idx = columns.index(col_name)
    candidates = []
    for offset in (-1, 0, 1, 2, -2):
        j = idx + offset
        if 0 <= j < len(columns):
            candidates.append(_parse_amount(row.get(columns[j])))
    non_zero = [v for v in candidates if v != 0]
    if len(non_zero) == 1:
        return non_zero[0]
    return 0.0


def _find_single_amount(row: pd.Series, exclude_cols: set) -> float:
    values = []
    for col, value in row.items():
        if col in exclude_cols:
            continue
        amount = _parse_amount(value)
        if amount != 0:
            values.append(amount)
    if len(values) == 1:
        return values[0]
    return 0.0


def _extract_movements(df: pd.DataFrame) -> List[dict]:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    mapping = _map_columns(df)
    columns = list(df.columns)

    if "date_operation" not in mapping or "libelle" not in mapping:
        raise HTTPException(status_code=400, detail="Colonnes obligatoires non trouvées (date/libellé)")

    movements = []
    for _, row in df.iterrows():
        date_operation = _parse_date(row.get(mapping["date_operation"]))
        libelle = str(row.get(mapping["libelle"]) or "").replace("\n", " ").strip()
        libelle_upper = libelle.upper()
        if "OPENING BALANCE" in libelle_upper or "CLOSING BALANCE" in libelle_upper:
            continue

        debit_col = mapping.get("debit")
        credit_col = mapping.get("credit")
        debit = _parse_amount(row.get(debit_col))
        credit = _parse_amount(row.get(credit_col))
        reference = str(row.get(mapping.get("reference")) or "").strip() or None

        if date_operation is None:
            continue

        if debit == 0 and debit_col and credit == 0:
            debit = _get_adjacent_amount(row, columns, debit_col)

        if credit == 0 and credit_col and debit == 0:
            credit = _get_adjacent_amount(row, columns, credit_col)

        if debit == 0 and credit == 0:
            exclude_cols = {
                mapping.get("date_operation"),
                mapping.get("date_valeur"),
                mapping.get("libelle"),
                mapping.get("reference"),
                debit_col,
                credit_col,
            }
            exclude_cols = {c for c in exclude_cols if c}
            fallback_amount = _find_single_amount(row, exclude_cols)
            if fallback_amount != 0:
                debit = fallback_amount

        if libelle == "" and debit == 0 and credit == 0:
            continue

        if libelle.upper().startswith("VIREMENT DOMESTIQUE RECU") and debit > 0 and credit == 0:
            credit = debit
            debit = 0.0

        movements.append({
            "date_operation": date_operation,
            "libelle": libelle or "(sans libellé)",
            "debit": debit,
            "credit": credit,
            "reference": reference,
        })

    if not movements:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté")

    return movements
