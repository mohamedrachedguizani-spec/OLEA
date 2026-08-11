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

    raw_clean = re.sub(r"[^0-9.,\-]", "", raw)

    # Gestion du format tunisien : virgule OU point comme séparateur décimal
    # En comptabilité tunisienne, les montants ont souvent 3 décimales (millimes)
    if "," in raw_clean and "." in raw_clean:
        last_comma = raw_clean.rfind(",")
        last_dot = raw_clean.rfind(".")
        if last_comma > last_dot:
            # 1.250,000 → virgule est le décimal
            raw_clean = raw_clean.replace(".", "")
            raw_clean = raw_clean.replace(",", ".")
        else:
            # 1,250.000 → point est le décimal
            raw_clean = raw_clean.replace(",", "")
    elif "," in raw_clean:
        # Si exactement 3 chiffres après virgule → décimal tunisien (millimes)
        parts = raw_clean.split(",")
        if len(parts) == 2 and len(parts[1]) == 3:
            raw_clean = raw_clean.replace(",", ".")
        else:
            raw_clean = raw_clean.replace(",", ".")
    elif "." in raw_clean:
        # Si exactement 3 chiffres après point → probablement aussi décimal tunisien
        parts = raw_clean.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            pass  # Garder le point comme décimal
        # Sinon : si plusieurs points → enlever les points (milliers)
        elif raw_clean.count(".") > 1:
            raw_clean = raw_clean.replace(".", "")

    if raw_clean in {"", ".", "-", "-."}:
        return 0.0
    try:
        amount = float(raw_clean)
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
    raw = str(value).strip()

    # --- Gestion des mois français (abréviés avec ou sans point) ---
    french_months = {
        'janvier': 1, 'janv': 1,
        'février': 2, 'fevrier': 2, 'févr': 2, 'fevr': 2,
        'mars': 3,
        'avril': 4, 'avr': 4,
        'mai': 5,
        'juin': 6,
        'juillet': 7, 'juil': 7,
        'août': 8, 'aout': 8,
        'septembre': 9, 'sept': 9,
        'octobre': 10, 'oct': 10,
        'novembre': 11, 'nov': 11,
        'décembre': 12, 'decembre': 12, 'déc': 12, 'dec': 12,
    }
    # Pattern : "01 juil. 26" ou "30 juin 26" ou "03 août 26"
    m = re.match(r'(\d{1,2})\s+([a-zA-Zéûôîâäëïöüùç]+)\.?\s+(\d{2,4})', raw, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower().rstrip('.')
        year = int(m.group(3))
        month = french_months.get(month_str)
        if month:
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                pass

    try:
        return date_parser.parse(raw, dayfirst=True).date()
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
# PARSER PDF ATB TEXTE BRUT (inchangé)
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
# PARSER PDF BIAT (texte brut + tableaux)
# =============================================================================

def _is_biat_text_format(lines: list) -> bool:
    sample = " ".join(lines[:150]).upper()
    has_biat = "BIAT" in sample or "BANQUE INTERNATIONALE ARABE" in sample
    has_releve = (
        "RELEV" in sample
        or "COMPTE MENSUEL" in sample
        or "EXTRAIT" in sample
        or "كشف" in sample
        or "كشفحساب" in sample
    )
    # Détection robuste du header BIAT même si "BIAT" est en image
    has_biat_header = (
        ("DATE OPÉ" in sample or "DATE OPE" in sample or "DATE OPE" in sample)
        and ("LIBELLÉ OPÉRATION" in sample or "LIBELLE OPERATION" in sample)
        and ("DATE VALEUR" in sample)
    )
    # Détection par tableau avec pipes
    has_pipe_table = any('|' in line and 'Date' in line for line in lines[:30])
    return (has_biat and has_releve) or has_biat_header or has_pipe_table


def _parse_pdf_biat_tables(pdf) -> pd.DataFrame:
    """
    Essaie d'extraire les tableaux BIAT (pages 2+ avec pipes).
    Retourne un DataFrame ou lève une exception.
    """
    all_rows = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables or []:
            if not table or len(table) < 2:
                continue
            # Chercher la ligne d'en-tête
            header_idx = None
            for idx, row in enumerate(table):
                if not row:
                    continue
                joined = " ".join(str(c or "").upper() for c in row)
                if ("DATE" in joined or "OPÉ" in joined or "OPE" in joined) and \
                   ("DÉBIT" in joined or "DEBIT" in joined) and \
                   ("CRÉDIT" in joined or "CREDIT" in joined):
                    header_idx = idx
                    break
            if header_idx is None:
                continue

            header = [str(c or "").strip() for c in table[header_idx]]
            # Nettoyer les en-têtes vides ou pipes
            header = [h.strip('|').strip() for h in header]
            header = [h for h in header if h]

            for row in table[header_idx + 1:]:
                if not row:
                    continue
                row = [str(c or "").strip().strip('|').strip() for c in row]
                # Filtrer les lignes vides ou de fin
                if all(not c for c in row):
                    continue
                if any("solde fin" in (c or "").lower() for c in row):
                    continue
                if any("sauf erreur" in (c or "").lower() for c in row):
                    continue

                # Mapper les colonnes par contenu
                date_op = None
                date_val = None
                libelle = ""
                ref = ""
                debit = 0.0
                credit = 0.0

                # Si le row a le bon nombre de colonnes, les assigner par position
                # Typiquement : [Date Opé, Libellé, Référence, Date valeur, Débit, Crédit]
                if len(row) >= 5:
                    date_op = _parse_date(row[0])
                    libelle = row[1] if len(row) > 1 else ""
                    ref = row[2] if len(row) > 2 else ""
                    date_val = _parse_date(row[3]) if len(row) > 3 else None
                    debit_str = row[4] if len(row) > 4 else ""
                    credit_str = row[5] if len(row) > 5 else ""

                    # Parfois débit et crédit sont inversés ou collés
                    debit_val = _parse_amount(debit_str)
                    credit_val = _parse_amount(credit_str)

                    # Si le montant est dans la colonne crédit mais pas débit
                    if debit_val == 0 and credit_val > 0:
                        debit = 0.0
                        credit = credit_val
                    elif debit_val > 0 and credit_val == 0:
                        debit = debit_val
                        credit = 0.0
                    elif debit_val < 0:
                        debit = abs(debit_val)
                        credit = 0.0
                    else:
                        debit = debit_val
                        credit = credit_val

                    if date_op:
                        all_rows.append({
                            "date_operation": date_op,
                            "date_valeur": date_val,
                            "reference": ref or None,
                            "libelle": libelle.strip() or "(sans libellé)",
                            "debit": debit,
                            "credit": credit,
                        })

    if not all_rows:
        raise HTTPException(status_code=400, detail="Aucun tableau BIAT détecté")

    return pd.DataFrame(all_rows)


def _parse_pdf_biat_text(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse BIAT : d'abord essaie les tableaux, puis fallback sur texte brut.
    """
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        # --- ÉTAPE 1 : Essayer les tableaux (pages 2+) ---
        try:
            df = _parse_pdf_biat_tables(pdf)
            if len(df) > 0:
                return df
        except HTTPException:
            pass

        # --- ÉTAPE 2 : Fallback texte brut (page 1 ou PDF sans tableaux) ---
        text = ""
        for page in pdf.pages:
            pt = page.extract_text()
            if pt:
                text += pt + "\n"

    if not text.strip():
        raise HTTPException(status_code=400, detail="PDF vide ou texte non extractible")

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Références : FT, CHG, TT, PDL, LD, ET (présent dans ce PDF)
    ref_pattern = r'(?:FT|CHG|TT|PDL|LD|ET)[A-Z0-9\\/_;.\-]+'
    date_pattern = r'\d{1,2}\s+[a-zA-Zéûôîâäëïöüùç]+\.?\s+\d{2,4}'
    line_re = re.compile(
        r'^(?P<date_op>' + date_pattern + r')\s+'
        r'(?P<libelle>.+?)\s+'
        r'(?P<ref>' + ref_pattern + r')\s+'
        r'(?P<date_val>' + date_pattern + r')\s+'
        r'(?P<amount>-?\d[\d\s.,]*)$',
        re.IGNORECASE
    )

    skip_patterns = [
        re.compile(r'^Date\s+Op[ée]', re.IGNORECASE),
        re.compile(r'^Libell[ée]\s+Op[ée]ration', re.IGNORECASE),
        re.compile(r'^R[ée]f[ée]rence$', re.IGNORECASE),
        re.compile(r'^Date\s+valeur', re.IGNORECASE),
        re.compile(r'^D[ée]bit$', re.IGNORECASE),
        re.compile(r'^Cr[ée]dit$', re.IGNORECASE),
        re.compile(r'^Solde\s+(d[ée]part|fin|actuel)', re.IGNORECASE),
        re.compile(r'^Page\s+\d+', re.IGNORECASE),
        re.compile(r'^BIAT$', re.IGNORECASE),
        re.compile(r'^#\s+Extrait\s+de\s+compte', re.IGNORECASE),
        re.compile(r'^Extrait\s+de\s+compte', re.IGNORECASE),
        re.compile(r'^Num[ée]ro\s+de\s+Compte', re.IGNORECASE),
        re.compile(r'^Devise', re.IGNORECASE),
        re.compile(r'^RIB', re.IGNORECASE),
        re.compile(r'^Cat[ée]gorie\s+Compte', re.IGNORECASE),
        re.compile(r'^Nom\s+du\s+Client', re.IGNORECASE),
        re.compile(r'^Sauf\s+erreur', re.IGNORECASE),
        re.compile(r'^Edit[ée]\s+le', re.IGNORECASE),
        re.compile(r'^Date\s*:', re.IGNORECASE),
        re.compile(r'^Heure\s*:', re.IGNORECASE),
    ]

    rows = []
    current = None

    for line in lines:
        if any(p.match(line) for p in skip_patterns):
            continue

        # Lignes de tableau avec pipes (si extract_tables a échoué mais pipes présents)
        if line.startswith('|') and line.endswith('|'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 5:
                date_op = _parse_date(parts[0])
                if date_op:
                    libelle = parts[1] if len(parts) > 1 else ""
                    ref = parts[2] if len(parts) > 2 else ""
                    date_val = _parse_date(parts[3]) if len(parts) > 3 else None
                    debit = _parse_amount(parts[4]) if len(parts) > 4 else 0.0
                    credit = _parse_amount(parts[5]) if len(parts) > 5 else 0.0
                    # Si montant négatif dans débit
                    if debit < 0:
                        debit = abs(debit)
                        credit = 0.0
                    rows.append({
                        "date_operation": date_op,
                        "date_valeur": date_val,
                        "reference": ref or None,
                        "libelle": libelle.strip() or "(sans libellé)",
                        "debit": debit,
                        "credit": credit,
                    })
                    continue

        m = line_re.match(line)
        if m:
            if current:
                rows.append(current)

            amount_val = _parse_amount(m.group('amount'))
            debit = abs(amount_val) if amount_val < 0 else 0.0
            credit = amount_val if amount_val > 0 else 0.0

            current = {
                'date_operation': _parse_date(m.group('date_op')),
                'date_valeur': _parse_date(m.group('date_val')),
                'reference': m.group('ref'),
                'libelle': m.group('libelle').strip(),
                'debit': debit,
                'credit': credit,
            }
        else:
            if current is not None:
                # C'est une suite de libellé
                current['libelle'] += ' ' + line.strip()

    if current:
        rows.append(current)

    if not rows:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le PDF BIAT")

    df_rows = []
    for r in rows:
        if r['date_operation'] is None:
            continue
        df_rows.append({
            'date_operation': r['date_operation'],
            'date_valeur': r['date_valeur'],
            'reference': r['reference'] or None,
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
        if "SOLDE DEPART" in libelle_upper or "SOLDE FIN" in libelle_upper:
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