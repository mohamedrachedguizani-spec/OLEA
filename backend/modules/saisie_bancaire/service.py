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


# --- ATB : parseur par POSITION des colonnes (sens débit/crédit lu dans la colonne, pas deviné) ---
_ATB_DAYMONTH_RE = re.compile(r"^\d{2}/\d{2}$")
_ATB_AMOUNT_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*\.\d{3}$|^-?\d+\.\d{3}$")
_ATB_PERIOD_RE = re.compile(r"Du\s+(\d{2}/\d{2}/\d{4})\s+au\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


def _atb_amount(txt: str) -> float:
    """'-43,201.896' -> -43201.896 (virgule = milliers, point = décimales)."""
    return float(txt.replace(",", ""))


def _atb_resolve_date(day_month: str, period_start, period_end, value_date):
    """Année de la date d'opération « JJ/MM » : celle qui tombe dans la période du relevé."""
    d, m = (int(x) for x in day_month.split("/"))
    candidates = []
    years = []
    if period_start and period_end:
        years = sorted({period_start.year, period_end.year})
    elif value_date:
        years = [value_date.year - 1, value_date.year, value_date.year + 1]
    for y in years:
        try:
            candidates.append(date(y, m, d))
        except ValueError:
            pass
    if not candidates:
        return None
    if period_start and period_end:
        inside = [c for c in candidates if period_start <= c <= period_end]
        if inside:
            return inside[0]
    ref = value_date or period_end
    return min(candidates, key=lambda c: abs((c - ref).days)) if ref else candidates[0]


def _parse_pdf_atb_positional(file_bytes: bytes) -> pd.DataFrame:
    """
    Extrait de compte ATB : Jour | D.Valeur | Référence | Libellé Mouvement | Débit | Crédit.
    - sens débit/crédit lu dans la colonne du montant (montants alignés à droite) ;
    - libellés multi-lignes regroupés ; année de « JJ/MM » déduite de la période « Du … au … » ;
    - « Opening Balance » / « Closing Balance » lus comme soldes (signe explicite), jamais comme mouvements ;
    - contrôle final : opening + crédits - débits == closing.
    """
    rows = []
    opening = closing = None
    period_start = period_end = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if period_start is None:
                m = _ATB_PERIOD_RE.search(text)
                if m:
                    period_start, period_end = _ubci_date(m.group(1)), _ubci_date(m.group(2))

            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            if not words:
                continue

            # En-tête de colonnes de la page
            hdr = {}
            for w in words:
                t = w["text"]
                if t == "Jour":
                    hdr["jour"] = w
                elif t in ("Débit", "Debit") and "debit" not in hdr:
                    hdr["debit"] = w
                elif t in ("Crédit", "Credit") and "credit" not in hdr:
                    hdr["credit"] = w
                elif t.startswith("Libell") and "lib" not in hdr:
                    hdr["lib"] = w
                elif t.startswith("Référence") and "ref" not in hdr:
                    hdr["ref"] = w
            if not all(k in hdr for k in ("jour", "debit", "credit", "lib", "ref")):
                continue
            hdr_top = hdr["jour"]["top"]
            lib_x = hdr["lib"]["x0"] - 4
            ref_x = hdr["ref"]["x0"] - 4
            val_x = hdr["jour"]["x1"] + 3
            split_x = (hdr["debit"]["x1"] + hdr["credit"]["x1"]) / 2
            amt_x = hdr["debit"]["x1"] - 70

            # Pied de page « Date : … Heure : … Page : … »
            cutoff = page.height
            for w in words:
                if w["text"] == "Heure" and w["top"] > hdr_top:
                    cutoff = min(cutoff, w["top"] - 4)
            body = [w for w in words if hdr_top + 6 < w["top"] < cutoff]

            body.sort(key=lambda w: (w["top"], w["x0"]))
            lines, cur, cur_top = [], [], None
            for w in body:
                if cur_top is None or abs(w["top"] - cur_top) <= 3.5:
                    cur.append(w)
                    cur_top = w["top"] if cur_top is None else cur_top
                else:
                    lines.append(sorted(cur, key=lambda x: x["x0"]))
                    cur, cur_top = [w], w["top"]
            if cur:
                lines.append(sorted(cur, key=lambda x: x["x0"]))

            current = None
            for ln in lines:
                t = [w["text"] for w in ln]
                anchored = (
                    len(ln) >= 3
                    and ln[0]["x0"] < val_x
                    and _ATB_DAYMONTH_RE.match(t[0])
                    and _UBCI_DATE_RE.match(t[1])
                )
                if anchored:
                    desc = " ".join(w["text"] for w in ln if lib_x <= w["x0"] < amt_x)
                    amts = [w for w in ln if w["x0"] >= amt_x and _ATB_AMOUNT_RE.match(w["text"])]
                    low = desc.lower()
                    if "opening balance" in low or "closing balance" in low:
                        if amts:
                            val = _atb_amount(amts[-1]["text"])
                            if "opening" in low:
                                opening = val
                            else:
                                closing = val
                        current = None
                        continue
                    current = {
                        "dm": t[0],
                        "val": _ubci_date(t[1]),
                        "ref": " ".join(w["text"] for w in ln[2:] if w["x0"] < lib_x),
                        "lib": [desc] if desc else [],
                        "amt": amts,
                    }
                    rows.append(current)
                elif current is not None:
                    cont = " ".join(w["text"] for w in ln if w["x0"] >= lib_x and w["x0"] < amt_x)
                    amts = [w for w in ln if w["x0"] >= amt_x and _ATB_AMOUNT_RE.match(w["text"])]
                    if cont:
                        current["lib"].append(cont)
                    if amts:
                        current["amt"].extend(amts)
            current = None

    out = []
    for r in rows:
        date_op = _atb_resolve_date(r["dm"], period_start, period_end, r["val"])
        if date_op is None or len(r["amt"]) != 1:
            raise HTTPException(
                status_code=400,
                detail="Ligne ATB illisible : {} {}".format(r["dm"], " ".join(r["lib"])),
            )
        a = r["amt"][0]
        val = abs(_atb_amount(a["text"]))
        is_credit = a["x1"] > split_x
        out.append({
            "date_operation": date_op,
            "date_valeur": r["val"],
            "reference": r["ref"].strip() or None,
            "libelle": " ".join(r["lib"]).strip() or "(sans libellé)",
            "debit": 0.0 if is_credit else val,
            "credit": val if is_credit else 0.0,
        })

    if not out:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le PDF ATB")
    df = pd.DataFrame(out)

    if opening is not None and closing is not None:
        expected = round(opening + df["credit"].sum() - df["debit"].sum(), 3)
        if abs(expected - closing) > 0.01:
            raise HTTPException(
                status_code=400,
                detail="Écart de contrôle ATB : solde final calculé {:.3f} vs relevé {:.3f} ({} mouvements extraits)".format(
                    expected, closing, len(df)
                ),
            )
    return df



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
    return (has_biat and has_releve) or has_biat_header or has_pipe_table or _is_biat_releve_format(lines) or _is_biat_extrait_format(lines)


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


# --- Format "Relevé de compte mensuel" BIAT (PDF texte, sans en-têtes lisibles) ---
_BIAT_AMOUNT_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{3}$")
_BIAT_VALUE_DATE_RE = re.compile(r"^\d{8}$")


def _is_biat_releve_format(lines: list) -> bool:
    """Détecte le relevé mensuel BIAT : lignes 'JJ MM libellé ref JJMMAAAA montant'."""
    row_re = re.compile(r"^\d{2}\s\d{2}\s.+\s\d{8}\s\d{1,3}(?:\.\d{3})*,\d{3}$")
    sample = lines[:200]
    nb_rows = sum(1 for l in sample if row_re.match(l))
    has_hint = any(l.upper().startswith(("SOLDE AU", "RIB :")) for l in sample)
    return nb_rows >= 3 and has_hint


def _parse_pdf_biat_releve(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse le relevé mensuel BIAT.
    Particularités :
      - la date d'opération est 'JJ MM' (sans année) -> l'année vient de la date du relevé ;
      - le sens (débit/crédit) n'est donné que par la POSITION X du montant
        (colonne Débit à gauche, colonne Crédit à droite) ;
      - la date de valeur est au format JJMMAAAA ;
      - le dernier mot du libellé est la référence.
    """
    rows = []
    opening_balance = None
    total_debit = total_credit = None
    stmt_year = stmt_month = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            if not words:
                continue
            split_x = page.width * 0.84  # frontière colonne Débit | Crédit

            # Date du relevé (ex. "31 12 2025") : bloc 'Date' en haut de page
            if stmt_year is None:
                txt = page.extract_text() or ""
                m = re.search(r"\b(\d{2})\s(\d{2})\s(20\d{2})\b", txt)
                if m:
                    stmt_month, stmt_year = int(m.group(2)), int(m.group(3))

            # Regroupement des mots par ligne (tolérance verticale 3 pt)
            words.sort(key=lambda w: (w["top"], w["x0"]))
            lines, cur, cur_top = [], [], None
            for w in words:
                if cur_top is None or abs(w["top"] - cur_top) <= 3:
                    cur.append(w)
                    cur_top = w["top"] if cur_top is None else cur_top
                else:
                    lines.append(sorted(cur, key=lambda x: x["x0"]))
                    cur, cur_top = [w], w["top"]
            if cur:
                lines.append(sorted(cur, key=lambda x: x["x0"]))

            for ln in lines:
                texts = [w["text"] for w in ln]
                joined = " ".join(texts)

                # Solde initial
                if joined.upper().startswith("SOLDE AU") and _BIAT_AMOUNT_RE.match(texts[-1]):
                    opening_balance = _parse_amount(texts[-1])
                    continue

                # Ligne de totaux (deux montants, aucune date)
                if all(_BIAT_AMOUNT_RE.match(t) for t in texts) and len(texts) == 2:
                    total_debit, total_credit = _parse_amount(texts[0]), _parse_amount(texts[1])
                    continue

                # Ligne de mouvement
                if len(ln) < 5:
                    continue
                if not (re.fullmatch(r"\d{2}", texts[0]) and re.fullmatch(r"\d{2}", texts[1])):
                    continue
                if ln[0]["x0"] > page.width * 0.15:
                    continue
                if not _BIAT_AMOUNT_RE.match(texts[-1]):
                    continue
                if not _BIAT_VALUE_DATE_RE.match(texts[-2]):
                    continue

                day, month = int(texts[0]), int(texts[1])
                year = stmt_year or datetime.now().year
                if stmt_month and month > stmt_month:  # relevé à cheval sur 2 années
                    year -= 1
                try:
                    date_op = date(year, month, day)
                except ValueError:
                    continue

                vd = texts[-2]
                try:
                    date_val = date(int(vd[4:8]), int(vd[2:4]), int(vd[0:2]))
                except ValueError:
                    date_val = None

                middle = texts[2:-2]
                if not middle:
                    continue
                if len(middle) >= 2:
                    reference, libelle = middle[-1], " ".join(middle[:-1])
                else:
                    reference, libelle = None, middle[0]

                amount = _parse_amount(texts[-1])
                is_credit = ln[-1]["x1"] > split_x
                rows.append({
                    "date_operation": date_op,
                    "date_valeur": date_val,
                    "reference": reference,
                    "libelle": libelle.strip() or "(sans libellé)",
                    "debit": 0.0 if is_credit else amount,
                    "credit": amount if is_credit else 0.0,
                })

    if not rows:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le relevé BIAT")

    df = pd.DataFrame(rows)

    # Contrôle de cohérence : le total Crédit du relevé inclut le solde initial
    if total_debit is not None and total_credit is not None:
        sum_d = round(df["debit"].sum(), 3)
        sum_c = round(df["credit"].sum() + (opening_balance or 0.0), 3)
        if abs(sum_d - total_debit) > 0.01 or abs(sum_c - total_credit) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Écart de contrôle BIAT : débit extrait {:.3f} vs relevé {:.3f} ; "
                    "crédit extrait (+solde initial) {:.3f} vs relevé {:.3f}"
                ).format(sum_d, total_debit, sum_c, total_credit),
            )
    return df



# --- Format « Extrait de compte » BIAT (export Détails Transactions) ---
_BIAT_EXTRAIT_DATE_RE = re.compile(r"^\d{2}$")
_BIAT_EXTRAIT_MONTH_RE = re.compile(r"^[A-Za-zéûôîâäëïöüùç]{3,9}\.?$")


def _is_biat_extrait_format(lines: list) -> bool:
    """Détecte l'export « Extrait de compte » (Numéro de Compte, Catégorie Compte, Solde départ au …)."""
    head = " ".join(lines[:60]).upper()
    return (
        "EXTRAIT DE COMPTE" in head
        and "CAT" in head and "COMPTE" in head
        and any(l.upper().startswith("SOLDE D") and " AU " in l.upper() for l in lines[:80])
    )


def _parse_pdf_biat_extrait(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse l'« Extrait de compte » BIAT par POSITION des mots (colonnes) :
    Date Opé | Libellé Opération (multi-lignes) | Référence | Date valeur | Débit | Crédit.
    - les montants débit sont négatifs (-4,165) ; les milliers sont séparés par des espaces ;
    - une opération = une ligne commençant par « JJ mois. AA » ; les lignes suivantes
      (sans date) complètent le libellé ;
    - contrôle final : solde départ + crédits - débits == solde fin.
    """
    rows = []
    opening = closing = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            if not words:
                continue
            footer_y = page.height - 60

            # Regroupement en lignes (tolérance verticale 3 pt)
            words.sort(key=lambda w: (w["top"], w["x0"]))
            lines, cur, cur_top = [], [], None
            for w in words:
                if cur_top is None or abs(w["top"] - cur_top) <= 3:
                    cur.append(w)
                    cur_top = w["top"] if cur_top is None else cur_top
                else:
                    lines.append(sorted(cur, key=lambda x: x["x0"]))
                    cur, cur_top = [w], w["top"]
            if cur:
                lines.append(sorted(cur, key=lambda x: x["x0"]))

            # Positions des colonnes lues dans l'en-tête de CETTE page
            lib_x, ref_x, val_x, deb_x, cre_x = 92.0, 220.0, 323.0, 400.0, 477.0
            for ln in lines:
                t = [w["text"] for w in ln]
                if t[:2] == ["Date", "Opé"] or (t and t[0] == "Date" and "Référence" in t):
                    for i, w in enumerate(ln):
                        if w["text"].startswith("Libell"):
                            lib_x = w["x0"] - 3
                        elif w["text"].startswith("Référence") or w["text"].startswith("Reference"):
                            ref_x = w["x0"] - 3
                        elif w["text"] == "valeur" and i > 0 and ln[i - 1]["text"] == "Date":
                            val_x = ln[i - 1]["x0"] - 3
                        elif w["text"].startswith("Débit") or w["text"].startswith("Debit"):
                            deb_x = w["x0"] - 4
                        elif w["text"].startswith("Crédit") or w["text"].startswith("Credit"):
                            cre_x = w["x0"] - 4
                    break
            mid_x = (deb_x + cre_x) / 2

            def amount_of(ws):
                """Montant signé (+crédit / -débit) à partir des mots de la zone montant."""
                if not ws:
                    return None
                raw = "".join(w["text"] for w in ws)
                val = _parse_amount(raw)
                if val == 0 and not re.search(r"[1-9]", raw):
                    return 0.0
                if raw.startswith("-"):
                    return -abs(val)
                return abs(val) if ws[0]["x0"] >= mid_x else -abs(val)

            current = None
            for ln in lines:
                if ln[0]["top"] >= footer_y:
                    current = None
                    continue
                t = [w["text"] for w in ln]
                low = " ".join(t).lower()

                # en-tête de tableau
                if t[:1] == ["Date"] and ("Référence" in t or "Reference" in t):
                    current = None
                    continue

                # soldes départ / fin
                m = re.match(r"^solde\s+(d[ée]part|fin)\b", low)
                if m:
                    amt_words = [w for w in ln if w["x0"] >= deb_x]
                    amt = amount_of(amt_words)
                    if m.group(1) == "fin":
                        closing = amt
                    else:
                        opening = amt
                    current = None
                    continue
                if low.startswith("sauf erreur"):
                    current = None
                    continue

                # nouvelle opération
                if (
                    len(ln) >= 3
                    and ln[0]["x0"] < lib_x
                    and _BIAT_EXTRAIT_DATE_RE.match(t[0])
                    and _BIAT_EXTRAIT_MONTH_RE.match(t[1])
                    and _BIAT_EXTRAIT_DATE_RE.match(t[2])
                ):
                    date_op = _parse_date(" ".join(t[:3]))
                    if date_op is None:
                        raise HTTPException(
                            status_code=400,
                            detail="Date illisible dans l'extrait BIAT : " + " ".join(t[:3]),
                        )
                    current = {"date_op": date_op, "lib": [], "ref": [], "val": [], "amt": []}
                    rows.append(current)
                    body = ln[3:]
                elif current is not None:
                    body = ln
                else:
                    continue

                for w in body:
                    x = w["x0"]
                    if x < lib_x:
                        continue
                    if x < ref_x:
                        current["lib"].append(w["text"])
                    elif x < val_x:
                        current["ref"].append(w["text"])
                    elif x < deb_x:
                        current["val"].append(w["text"])
                    else:
                        current["amt"].append(w)

    out = []
    for r in rows:
        amount = amount_of(r["amt"])
        if amount is None or amount == 0:
            raise HTTPException(
                status_code=400,
                detail="Montant introuvable pour l'opération du {} : {}".format(
                    r["date_op"], " ".join(r["lib"])
                ),
            )
        out.append({
            "date_operation": r["date_op"],
            "date_valeur": _parse_date(" ".join(r["val"])) if r["val"] else None,
            "reference": " ".join(r["ref"]).strip() or None,
            "libelle": " ".join(r["lib"]).strip() or "(sans libellé)",
            "debit": abs(amount) if amount < 0 else 0.0,
            "credit": amount if amount > 0 else 0.0,
        })

    if not out:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans l'extrait BIAT")

    df = pd.DataFrame(out)

    # Contrôle de cohérence : solde départ + crédits - débits = solde fin
    if opening is not None and closing is not None:
        expected = round(opening + df["credit"].sum() - df["debit"].sum(), 3)
        if abs(expected - closing) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Écart de contrôle BIAT : solde fin calculé {:.3f} vs relevé {:.3f} "
                    "({} mouvements extraits)"
                ).format(expected, closing, len(df)),
            )
    return df



# --- Format « Relevé de compte mensuel » BIAT 2026 (dates JJ/MM/AAAA, tableau à 6 colonnes) ---
_BIAT_M26_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _biat_m26_date(txt: str):
    try:
        d, m, y = txt.split("/")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _parse_pdf_biat_mensuel_2026(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse le relevé mensuel BIAT nouvelle présentation :
      Date | Libellé de l'opération (multi-lignes) | Référence | Date de valeur | Débit | Crédit
    - dates au format JJ/MM/AAAA ;
    - le sens est donné par la POSITION du montant (colonne Débit / Crédit) ;
    - « Solde au JJ/MM/AAAA » : solde initial, placé dans la colonne Débit s'il est débiteur ;
    - ligne « Totaux » : le total de la colonne du solde initial INCLUT ce solde initial ;
    - contrôle final : solde initial + crédits - débits == solde final.
    """
    rows = []
    opening = closing = None
    tot_debit = tot_credit = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            if not words:
                continue
            W = page.width
            lib_x, ref_x, val_x, deb_x, split_x = W * 0.115, W * 0.45, W * 0.62, W * 0.74, W * 0.89

            # Coupure : pied de page (Totaux / mentions légales)
            cutoff = page.height
            for w in words:
                if w["text"] == "Totaux" and w["x0"] < W * 0.6:
                    cutoff = min(cutoff, w["top"] - 12)
                if w["text"].startswith("dépôts") and w["x0"] < W * 0.2 and w["top"] > page.height * 0.6:
                    cutoff = min(cutoff, w["top"] - 2)
            body_words = [w for w in words if w["top"] < cutoff]

            def signed(ws):
                if not ws:
                    return None
                val = _parse_amount("".join(w["text"] for w in ws))
                return abs(val) if ws[-1]["x1"] > split_x else -abs(val)

            # Totaux et solde final (zone de pied de tableau)
            for w in words:
                if w["text"] == "Totaux" and w["x0"] < W * 0.6:
                    zone = [a for a in words if abs(a["top"] - w["top"]) <= 8 and a["x0"] >= deb_x - 40]
                    d = [a for a in zone if a["x1"] <= split_x]
                    c = [a for a in zone if a["x1"] > split_x]
                    if d:
                        tot_debit = abs(signed(d))
                    if c:
                        tot_credit = abs(signed(c))
                if w["text"] == "Solde" and w["x0"] < W * 0.6 and w["top"] > cutoff:
                    zone = [a for a in words if abs(a["top"] - w["top"]) <= 8 and a["x0"] >= deb_x - 40]
                    if zone:
                        closing = signed(zone)

            # Regroupement en lignes (tolérance verticale 3 pt)
            body_words.sort(key=lambda w: (w["top"], w["x0"]))
            lines, cur, cur_top = [], [], None
            for w in body_words:
                if cur_top is None or abs(w["top"] - cur_top) <= 5:
                    cur.append(w)
                    cur_top = w["top"] if cur_top is None else cur_top
                else:
                    lines.append(sorted(cur, key=lambda x: x["x0"]))
                    cur, cur_top = [w], w["top"]
            if cur:
                lines.append(sorted(cur, key=lambda x: x["x0"]))

            current = None
            for ln in lines:
                t = [w["text"] for w in ln]
                low = " ".join(t).lower()

                # solde initial : « Solde au 30/04/2026   606 817,304 »
                if "solde" in t and "au" in [x.lower() for x in t]:
                    amt_words = [w for w in ln if w["x0"] >= deb_x - 40 and re.match(r"^[\d,]+$", w["text"])]
                    if amt_words and any(_BIAT_M26_DATE_RE.match(x) for x in t):
                        opening = signed(amt_words)
                        current = None
                        continue

                if ln[0]["x0"] < lib_x and _BIAT_M26_DATE_RE.match(t[0]):
                    date_op = _biat_m26_date(t[0])
                    if date_op is None:
                        raise HTTPException(status_code=400, detail="Date illisible dans le relevé BIAT : " + t[0])
                    current = {"date_op": date_op, "lib": [], "ref": [], "val": [], "amt": []}
                    rows.append(current)
                    body = ln[1:]
                elif current is not None:
                    body = ln
                else:
                    continue

                for w in body:
                    x = w["x0"]
                    if x < lib_x:
                        continue
                    if x < ref_x:
                        current["lib"].append(w["text"])
                    elif x < val_x:
                        current["ref"].append(w["text"])
                    elif x < deb_x:
                        current["val"].append(w["text"])
                    else:
                        current["amt"].append(w)
            # une opération ne continue jamais sur la page suivante sans nouvelle date
            current = None

    out = []
    for r in rows:
        if not r["amt"]:
            raise HTTPException(
                status_code=400,
                detail="Montant introuvable pour l'opération du {} : {}".format(r["date_op"], " ".join(r["lib"])),
            )
        val = _parse_amount("".join(w["text"] for w in r["amt"]))
        is_credit = r["amt"][-1]["x1"] > W * 0.89
        out.append({
            "date_operation": r["date_op"],
            "date_valeur": _biat_m26_date(" ".join(r["val"])) if r["val"] else None,
            "reference": " ".join(r["ref"]).strip() or None,
            "libelle": " ".join(r["lib"]).strip() or "(sans libellé)",
            "debit": 0.0 if is_credit else abs(val),
            "credit": abs(val) if is_credit else 0.0,
        })

    if not out:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le relevé BIAT")
    df = pd.DataFrame(out)

    problems = []
    if opening is not None and closing is not None:
        expected = round(opening + df["credit"].sum() - df["debit"].sum(), 3)
        if abs(expected - closing) > 0.01:
            problems.append("solde final calculé {:.3f} vs relevé {:.3f}".format(expected, closing))
    if opening is not None and tot_debit is not None and tot_credit is not None:
        exp_d = round(df["debit"].sum() + (abs(opening) if opening < 0 else 0.0), 3)
        exp_c = round(df["credit"].sum() + (opening if opening > 0 else 0.0), 3)
        if abs(exp_d - tot_debit) > 0.01 or abs(exp_c - tot_credit) > 0.01:
            problems.append(
                "totaux débit {:.3f}/{:.3f}, crédit {:.3f}/{:.3f} (extrait/relevé)".format(
                    exp_d, tot_debit, exp_c, tot_credit)
            )
    if problems:
        raise HTTPException(
            status_code=400,
            detail="Écart de contrôle BIAT : " + " ; ".join(problems) + " ({} mouvements extraits)".format(len(df)),
        )
    return df



def _parse_pdf_biat_text(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse BIAT : d'abord essaie les tableaux, puis fallback sur texte brut.
    """
    # --- ÉTAPE 0a : « Extrait de compte » BIAT (colonnes par position + contrôle des soldes) ---
    try:
        return _parse_pdf_biat_extrait(file_bytes)
    except HTTPException as exc:
        if "Écart de contrôle" in str(exc.detail):
            raise
    except Exception:
        pass

    # --- ÉTAPE 0b : relevé mensuel BIAT 2026 (JJ/MM/AAAA, 6 colonnes) ---
    try:
        return _parse_pdf_biat_mensuel_2026(file_bytes)
    except HTTPException as exc:
        if "Écart de contrôle" in str(exc.detail):
            raise
    except Exception:
        pass

    # --- ÉTAPE 0 : relevé mensuel BIAT (positions X des colonnes) ---
    try:
        return _parse_pdf_biat_releve(file_bytes)
    except HTTPException as exc:
        if "Écart de contrôle" in str(exc.detail):
            raise
    except Exception:
        pass

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

# --- UBCI : « Relevé de compte client » (tableau à 6 colonnes) ---
_UBCI_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_UBCI_OPENING_RE = re.compile(
    r"SOLDE\s+(DEBITEUR|CREDITEUR)\s+AU\s+(\d{2}/\d{2}/\d{4})\s+(-?\d{1,3}(?:\.\d{3})*,\d{3})",
    re.IGNORECASE,
)


def _ubci_amount(txt):
    """'-239.894,105' -> -239894.105 ; vide -> None."""
    txt = (txt or "").strip().replace(" ", "")
    if not txt:
        return None
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _ubci_date(txt):
    try:
        d, m, y = (txt or "").strip().split("/")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _is_ubci_format(raw_text: str) -> bool:
    up = raw_text.upper()
    return (
        ("UBCI" in up or "UNION BANCAIRE POUR LE COMMERCE" in up)
        and "REF BANQUE" in up
        and "NATURES DES OP" in up
    )


def _parse_pdf_ubci(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse le relevé UBCI. Le tableau PDF est lu cellule par cellule :
    Date opération | Natures des opérations | Débit | Crédit | Date valeur | Ref Banque.
    Débit et Crédit sont des colonnes distinctes (aucune déduction de signe nécessaire).
    Contrôles : solde initial + crédits - débits == solde de clôture, et totaux Débit/Crédit.
    """
    rows = []
    opening = closing = None
    tot_debit = tot_credit = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = _UBCI_OPENING_RE.search(text)
            if m and opening is None:
                val = _ubci_amount(m.group(3))
                if val is not None:
                    opening = -abs(val) if m.group(1).upper() == "DEBITEUR" else abs(val)

            for table in page.extract_tables() or []:
                for row in table:
                    if not row or len(row) < 4:
                        continue
                    cells = [(c or "").strip() for c in row]
                    first = cells[0].upper()
                    if first.startswith("TOTAL DU DEBIT"):
                        nums = [_ubci_amount(c) for c in cells[1:]]
                        nums = [n for n in nums if n is not None]
                        if len(nums) >= 2:
                            tot_debit, tot_credit = nums[0], nums[1]
                        continue
                    if first.startswith("SOLDE DE CLOTURE"):
                        nums = [_ubci_amount(c) for c in cells[1:]]
                        nums = [n for n in nums if n is not None]
                        if nums:
                            closing = nums[0]
                        continue
                    if len(cells) < 6 or not _UBCI_DATE_RE.match(cells[0]):
                        continue

                    date_op = _ubci_date(cells[0])
                    debit = _ubci_amount(cells[2])
                    credit = _ubci_amount(cells[3])
                    libelle = " ".join(cells[1].split())
                    if date_op is None or (debit is None and credit is None):
                        raise HTTPException(
                            status_code=400,
                            detail="Ligne UBCI illisible : {} {}".format(cells[0], libelle),
                        )
                    rows.append({
                        "date_operation": date_op,
                        "date_valeur": _ubci_date(cells[4]),
                        "reference": cells[5] or None,
                        "libelle": libelle or "(sans libellé)",
                        "debit": abs(debit) if debit else 0.0,
                        "credit": abs(credit) if credit else 0.0,
                    })

    if not rows:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans le relevé UBCI")
    df = pd.DataFrame(rows)

    problems = []
    if opening is not None and closing is not None:
        expected = round(opening + df["credit"].sum() - df["debit"].sum(), 3)
        if abs(expected - closing) > 0.01:
            problems.append("solde de clôture calculé {:.3f} vs relevé {:.3f}".format(expected, closing))
    if tot_debit is not None and tot_credit is not None:
        sd, sc = round(df["debit"].sum(), 3), round(df["credit"].sum(), 3)
        if abs(sd - tot_debit) > 0.01 or abs(sc - tot_credit) > 0.01:
            problems.append(
                "totaux débit {:.3f}/{:.3f}, crédit {:.3f}/{:.3f} (extrait/relevé)".format(sd, tot_debit, sc, tot_credit)
            )
    if problems:
        raise HTTPException(
            status_code=400,
            detail="Écart de contrôle UBCI : " + " ; ".join(problems) + " ({} mouvements extraits)".format(len(df)),
        )
    return df



# --- UBCI : export e-banking « UBank – Extrait de compte » (colonnes sans bordures) ---
_UBANK_OPENING_RE = re.compile(
    r"Solde\s+d[ée]but\s+de\s+p[ée]riode\s*:?\s*(?:TND)?\s*(-?\d[\d\s.]*,\d{3})", re.IGNORECASE
)
_UBANK_CLOSING_RE = re.compile(
    r"Solde\s+actuel\s*:?\s*(?:TND)?\s*(-?\d[\d\s.]*,\d{3})", re.IGNORECASE
)


def _is_ubank_format(raw_text: str) -> bool:
    up = raw_text.upper()
    return "UBANK" in up and "DATE OPÉRATION" in up.replace("OPERATION", "OPÉRATION") and "SOLDE ACTUEL" in up


def _parse_pdf_ubank(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse l'export e-banking UBCI (UBank). Pas de lignes de tableau : colonnes lues par POSITION.
      Date Opération | Description (multi-lignes) | Débit | Crédit | Date Valeur
    - les montants sont alignés à gauche sous l'en-tête de leur colonne (Débit puis Crédit) ;
    - solde initial = « Solde début de période », solde final = « Solde actuel » (signes explicites) ;
    - contrôle final : solde initial + crédits - débits == solde actuel.
    """
    rows = []
    opening = closing = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if opening is None:
                m = _UBANK_OPENING_RE.search(text)
                if m:
                    opening = _ubci_amount(m.group(1))
            if closing is None:
                m = _UBANK_CLOSING_RE.search(text)
                if m:
                    closing = _ubci_amount(m.group(1))

            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            if not words:
                continue

            # Positions des colonnes lues dans l'en-tête de la page
            deb_x = cre_x = val_x = desc_x = None
            hdr_top = None
            for i, w in enumerate(words):
                t = w["text"]
                if t == "Débit" and deb_x is None:
                    deb_x, hdr_top = w["x0"], w["top"]
                elif t == "Crédit" and cre_x is None:
                    cre_x = w["x0"]
                elif t == "Description" and desc_x is None:
                    desc_x = w["x0"]
                elif t == "Date" and val_x is None and i + 1 < len(words) and words[i + 1]["text"] == "Valeur":
                    val_x = w["x0"]
            if deb_x is None or cre_x is None or val_x is None or desc_x is None:
                continue
            amt_start = deb_x - 8
            mid_x = (deb_x + cre_x) / 2
            val_start = val_x - 8

            # Pied de page « Ce document est généré par UBank … »
            cutoff = page.height
            for w in words:
                if w["text"] == "Ce" and w["top"] > hdr_top:
                    nxt = [x for x in words if abs(x["top"] - w["top"]) < 3 and x["x0"] > w["x0"]]
                    if nxt and nxt[0]["text"] == "document":
                        cutoff = min(cutoff, w["top"] - 4)
            body = [w for w in words if hdr_top + 8 < w["top"] < cutoff]

            body.sort(key=lambda w: (w["top"], w["x0"]))
            lines, cur, cur_top = [], [], None
            for w in body:
                if cur_top is None or abs(w["top"] - cur_top) <= 3:
                    cur.append(w)
                    cur_top = w["top"] if cur_top is None else cur_top
                else:
                    lines.append(sorted(cur, key=lambda x: x["x0"]))
                    cur, cur_top = [w], w["top"]
            if cur:
                lines.append(sorted(cur, key=lambda x: x["x0"]))

            current = None
            for ln in lines:
                first = ln[0]
                if first["x0"] < desc_x - 10 and _UBCI_DATE_RE.match(first["text"]):
                    current = {"date_op": _ubci_date(first["text"]), "desc": [], "amt": [], "val": []}
                    rows.append(current)
                    ln = ln[1:]
                elif current is None:
                    continue
                for w in ln:
                    x = w["x0"]
                    if x < desc_x - 5:
                        continue
                    if x < amt_start:
                        current["desc"].append(w["text"])
                    elif x < val_start:
                        current["amt"].append(w)
                    else:
                        current["val"].append(w["text"])
            current = None

    out = []
    for r in rows:
        if r["date_op"] is None or not r["amt"]:
            raise HTTPException(
                status_code=400,
                detail="Ligne UBank illisible : {} {}".format(r["date_op"], " ".join(r["desc"])),
            )
        w = r["amt"][0]
        val = _ubci_amount("".join(a["text"] for a in r["amt"]))
        if val is None or val == 0:
            raise HTTPException(
                status_code=400,
                detail="Montant illisible pour l'opération du {} : {}".format(r["date_op"], " ".join(r["desc"])),
            )
        is_credit = w["x0"] >= mid_x
        out.append({
            "date_operation": r["date_op"],
            "date_valeur": _ubci_date(" ".join(r["val"])) if r["val"] else None,
            "reference": (re.search(r"\b\d{15,16}\b", " ".join(r["desc"])) or [None])[0],
            "libelle": " ".join(r["desc"]).strip() or "(sans libellé)",
            "debit": 0.0 if is_credit else abs(val),
            "credit": abs(val) if is_credit else 0.0,
        })

    if not out:
        raise HTTPException(status_code=400, detail="Aucun mouvement détecté dans l'extrait UBCI")
    df = pd.DataFrame(out)

    if opening is not None and closing is not None:
        expected = round(opening + df["credit"].sum() - df["debit"].sum(), 3)
        if abs(expected - closing) > 0.01:
            raise HTTPException(
                status_code=400,
                detail="Écart de contrôle UBCI : solde actuel calculé {:.3f} vs extrait {:.3f} ({} mouvements extraits)".format(
                    expected, closing, len(df)
                ),
            )
    return df



def _parse_pdf(file_bytes: bytes) -> pd.DataFrame:
    raw_text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pt = page.extract_text()
            if pt:
                raw_text += pt + "\n"

    raw_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    if _is_ubank_format(raw_text):
        try:
            return _parse_pdf_ubank(file_bytes)
        except HTTPException as exc:
            if "Écart de contrôle" in str(exc.detail):
                raise

    if _is_ubci_format(raw_text):
        try:
            return _parse_pdf_ubci(file_bytes)
        except HTTPException as exc:
            if "Écart de contrôle" in str(exc.detail):
                raise

    if _is_biat_text_format(raw_lines):
        try:
            return _parse_pdf_biat_text(file_bytes)
        except HTTPException as exc:
            if "Écart de contrôle" in str(exc.detail):
                raise

    if _is_atb_text_format(raw_lines):
        try:
            return _parse_pdf_atb_positional(file_bytes)
        except HTTPException as exc:
            if "Écart de contrôle" in str(exc.detail):
                raise
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
    except HTTPException as exc:
        if "Écart de contrôle" in str(exc.detail):
            raise

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