from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from datetime import date, datetime
from typing import List, Optional
import csv
import io
import re
import unicodedata

import pandas as pd
import pdfplumber
from dateutil import parser as date_parser

from database import db
from modules.auth.dependencies import get_current_user, restrict_superadmin
from modules.audit.service import log_audit_action
from .models import (
    BankReconciliationBatch,
    BankReconciliationMovement,
    BankReconciliationUploadResponse,
    BankReconciliationSageGenerationRequest,
    BankReconciliationSageLine,
    BankReconciliationSageLinesResponse,
    BankReconciliationSageSaveResponse,
)


router = APIRouter(
    tags=["Rapprochement Bancaire"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("rapprochement_bancaire"))],
)


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

    # --- Format ATB tunisien : virgule = milliers, point = décimal ---
    # Ex: 4,433.148 → 4433.148  |  2,100.000 → 2100.0  |  43,201.896 → 43201.896
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
        raw = re.sub(r"[^0-9.\-]", "", raw)
    elif "," in raw:
        # Ancienne logique : format européen, virgule = décimal
        raw = raw.replace(",", ".")
        raw = re.sub(r"[^0-9.\-]", "", raw)
    else:
        # Ancienne logique : point = décimal (anglais) ou entier
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
# PARSER PDF ATB TEXTE BRUT (relevé sans tableau structuré)
# =============================================================================

def _is_atb_text_format(lines: list) -> bool:
    """Détecte si le PDF est un relevé ATB au format texte brut."""
    header_re = re.compile(
        r'Jour\s+D\.Valeur\s+Référence\s+Libellé\s+Mouvement\s+Débit\s+Crédit',
        re.IGNORECASE,
    )
    for line in lines:
        if header_re.search(line):
            return True
    return False


# --- Patterns de classification Débit / Crédit (priorité Débit > Crédit) ---
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
    """Classifie un mouvement ATB en 'debit' ou 'credit'."""
    lu = libelle.upper()
    for pat in _DEBIT_PATTERNS:
        if pat.search(lu):
            return "debit"
    for pat in _CREDIT_PATTERNS:
        if pat.search(lu):
            return "credit"
    return "unknown"


def _parse_pdf_atb_text(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse les relevés ATB 'texte brut' où chaque mouvement = 1 ligne :
      JJ/MM  DD/MM/YYYY  REFERENCE  Libellé  MONTANT
    Une seule colonne de montant par ligne (Débit OU Crédit).
    """
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

    # Regex principale : Jour  D.Valeur  [reste = Ref + Libellé + Montant]
    line_re = re.compile(r'^(\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$')
    ref_re = re.compile(r'^(FT|TT|CHG|ATB|TR)\w+$')

    # Lignes d'en-tête / pied de page à ignorer (ancre ^ obligatoire)
    skip_patterns = [
        re.compile(r'^Jour\s+D\.Valeur', re.IGNORECASE),
        re.compile(r'^Opening\s+Balance', re.IGNORECASE),
        re.compile(r'^Closing\s+Balance', re.IGNORECASE),
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

    rows = []

    for line in lines:
        # Skip lignes parasites (header/footer)
        if any(p.match(line) for p in skip_patterns):
            continue

        m = line_re.match(line)
        if not m:
            continue

        jour = m.group(1)
        date_valeur = m.group(2)
        rest = m.group(3).strip()

        tokens = rest.split()

        # --- Référence ---
        ref = ""
        if tokens and ref_re.match(tokens[0]):
            ref = tokens[0]
            tokens = tokens[1:]

        if not tokens:
            continue

        # --- Montant (dernier token) ---
        amount_str = tokens[-1]
        amount = _parse_amount(amount_str)

        # Si le dernier token n'est pas un montant valide, on ignore la ligne
        if amount == 0 and not re.match(r'^[\d\s\-\u2013\u2014,.]+$', amount_str):
            continue

        # --- Libellé ---
        libelle = " ".join(tokens[:-1]) if len(tokens) > 1 else ""

        # --- Dates ---
        year = date_valeur.split("/")[-1]
        try:
            date_op = datetime.strptime(f"{jour}/{year}", "%d/%m/%Y").date()
        except ValueError:
            date_op = datetime.strptime(date_valeur, "%d/%m/%Y").date()
        date_val = datetime.strptime(date_valeur, "%d/%m/%Y").date()

        # --- Débit / Crédit (classification par libellé) ---
        movement_type = _classify_atb_movement(libelle)
        debit = 0.0
        credit = 0.0

        if movement_type == "debit":
            debit = amount
        elif movement_type == "credit":
            credit = amount
        else:
            # Inconnu : par défaut Débit (conservateur pour commissions/frais)
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


def _parse_pdf(file_bytes: bytes) -> pd.DataFrame:
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

    if header is not None:
        safe_rows = [
            _normalize_row_length(row, len(header))
            for row in rows
        ]
        df = pd.DataFrame(safe_rows, columns=header)
        return df

    # =================================================================
    # FALLBACK : relevé ATB au format texte brut (sans tableau)
    # =================================================================
    try:
        return _parse_pdf_atb_text(file_bytes)
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
        debit_col = mapping.get("debit")
        credit_col = mapping.get("credit")
        debit = _parse_amount(row.get(debit_col))
        credit = _parse_amount(row.get(credit_col))
        reference = str(row.get(mapping.get("reference")) or "").strip() or None

        if date_operation is None:
            continue

        # --- FIX : empêcher la copie du montant dans l'autre colonne ---
        # Si un montant est déjà présent dans debit OU credit, on ne cherche
        # pas de fallback adjacent pour l'autre colonne.
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


@router.post("/rapprochement-bancaire/upload", response_model=BankReconciliationUploadResponse)
def upload_bank_reconciliation(
    request: Request,
    file: UploadFile = File(...),
    periode_debut: Optional[str] = Form(None),
    periode_fin: Optional[str] = Form(None),
    compte_banque: str = Form(...),
    compte_comptable: str = Form(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Fichier manquant")

    raw_bytes = file.file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Fichier vide")

    file_name = file.filename
    file_type = (file.content_type or "").lower()
    extension = (file.filename.split(".")[-1] or "").lower()

    parsed_periode_debut = _parse_date(periode_debut) if periode_debut else None
    parsed_periode_fin = _parse_date(periode_fin) if periode_fin else None

    if extension in {"xlsx", "xls"}:
        df = pd.read_excel(io.BytesIO(raw_bytes), dtype=str)
    elif extension in {"csv", "txt"}:
        content = raw_bytes.decode("utf-8", errors="ignore")
        df = _parse_csv_text(content)
    elif extension in {"pdf"} or "pdf" in file_type:
        df = _parse_pdf(raw_bytes)
    else:
        raise HTTPException(status_code=400, detail="Format non supporté")

    movements = _extract_movements(df)

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bank_reconciliation_batches
            (periode_debut, periode_fin, compte_banque, compte_comptable, file_name, file_type, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'extracted')
            """,
            (
                parsed_periode_debut,
                parsed_periode_fin,
                compte_banque.strip(),
                compte_comptable.strip(),
                file_name,
                extension or file_type or "unknown",
            ),
        )
        batch_id = cursor.lastrowid

        cursor.executemany(
            """
            INSERT INTO bank_reconciliation_movements
            (batch_id, date_operation, reference, libelle, debit, credit)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    batch_id,
                    m["date_operation"],
                    m["reference"],
                    m["libelle"],
                    m["debit"],
                    m["credit"],
                )
                for m in movements
            ],
        )

        cursor.execute(
            "SELECT * FROM bank_reconciliation_batches WHERE id = %s",
            (batch_id,),
        )
        batch_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT * FROM bank_reconciliation_movements
            WHERE batch_id = %s
            ORDER BY date_operation ASC, id ASC
            LIMIT 50
            """,
            (batch_id,),
        )
        preview = cursor.fetchall()

    log_audit_action(
        user=user,
        action="upload",
        module="rapprochement_bancaire",
        entity_type="bank_reconciliation_batch",
        entity_id=str(batch_id),
        detail={
            "file_name": file_name,
            "compte_banque": compte_banque,
            "compte_comptable": compte_comptable,
            "total_mouvements": len(movements),
        },
        request=request,
    )

    return {
        "batch": batch_row,
        "total_mouvements": len(movements),
        "preview": preview,
    }


@router.get("/rapprochement-bancaire/batches/{batch_id}/movements", response_model=List[BankReconciliationMovement])
def get_bank_reconciliation_movements(batch_id: int):
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM bank_reconciliation_movements WHERE batch_id = %s ORDER BY date_operation ASC, id ASC",
            (batch_id,),
        )
        return cursor.fetchall()


@router.get("/rapprochement-bancaire/batches/{batch_id}", response_model=BankReconciliationBatch)
def get_bank_reconciliation_batch(batch_id: int):
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM bank_reconciliation_batches WHERE id = %s",
            (batch_id,),
        )
        batch = cursor.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch introuvable")
        return batch


@router.post(
    "/rapprochement-bancaire/batches/{batch_id}/sage-lines",
    response_model=BankReconciliationSageLinesResponse,
)
def generate_sage_lines(
    batch_id: int,
    payload: BankReconciliationSageGenerationRequest,
):
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM bank_reconciliation_batches WHERE id = %s",
            (batch_id,),
        )
        batch = cursor.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch introuvable")

        cursor.execute(
            """
            SELECT * FROM bank_reconciliation_movements
            WHERE batch_id = %s
            ORDER BY date_operation ASC, id ASC
            """,
            (batch_id,),
        )
        movements = cursor.fetchall()

    compte_banque = (batch.get("compte_banque") or "").strip()
    compte_comptable = (batch.get("compte_comptable") or "").strip()
    numero_piece = f"{compte_comptable}-{date.today():%d%m%Y}"
    contreparties = payload.contreparties or {}
    default_contrepartie = (payload.contrepartie_compte or "").strip() or None
    tiers_by_movement = payload.tiers_by_movement or {}
    sections_by_movement = payload.sections_by_movement or {}

    lines: List[BankReconciliationSageLine] = []

    for mov in movements:
        movement_id = int(mov["id"])
        date_ecriture = mov["date_operation"]
        libelle = mov["libelle"]
        debit = float(mov["debit"] or 0)
        credit = float(mov["credit"] or 0)

        contrepartie_compte = contreparties.get(movement_id) or default_contrepartie
        contrepartie_tiers = tiers_by_movement.get(movement_id) or payload.tiers
        contrepartie_section = sections_by_movement.get(movement_id) or payload.section_analytique

        line1_tiers = tiers_by_movement.get(movement_id) or payload.tiers
        line1_section = sections_by_movement.get(movement_id) or payload.section_analytique

        # Inversement du principe débit/crédit entre la Banque (relevé) et la comptabilité de l'entreprise (Journal Banque).
        # Un débit sur le relevé de la banque est un crédit dans la comptabilité de l'entreprise (dépense), et inversement.
        lines.append(
            BankReconciliationSageLine(
                movement_id=movement_id,
                line_no=1,
                societe="TN01",
                journal=compte_banque,
                date_ecriture=date_ecriture,
                compte=compte_comptable,
                tiers=line1_tiers,
                debit=credit,  # Relevé Crédit -> Entreprise Débit (encaissement)
                credit=debit,  # Relevé Débit -> Entreprise Crédit (décaissement)
                section_analytique=line1_section,
                numero_piece=numero_piece,
                libelle=libelle,
                devise="TND",
                type_piece="BQ",
            )
        )

        lines.append(
            BankReconciliationSageLine(
                movement_id=movement_id,
                line_no=2,
                societe="TN01",
                journal=compte_banque,
                date_ecriture=date_ecriture,
                compte=contrepartie_compte,
                tiers=contrepartie_tiers,
                debit=debit,   # L2 a le débit/crédit opposé de L1
                credit=credit,
                section_analytique=contrepartie_section,
                numero_piece=numero_piece,
                libelle=libelle,
                devise="TND",
                type_piece="BQ",
            )
        )

    return {
        "batch_id": batch_id,
        "lines": lines,
    }


def _format_amount(value: float) -> str:
    if value == 0 or value == 0.0:
        return ""
    return str(value).replace(".", ",")


def _build_sage_csv(lines: List[BankReconciliationSageLine]) -> str:
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Société",
        "Journal",
        "Date écriture",
        "Code Compte",
        "Tiers",
        "Débit",
        "Crédit",
        "Section analytique",
        "N° de pièce",
        "Libellé écriture",
        "Devise",
        "Type de pièce",
    ])
    for line in lines:
        writer.writerow([
            line.societe,
            line.journal,
            line.date_ecriture.strftime("%d/%m/%Y"),
            line.compte or "",
            line.tiers or "",
            _format_amount(line.debit),
            _format_amount(line.credit),
            line.section_analytique or "",
            line.numero_piece,
            line.libelle,
            line.devise,
            line.type_piece,
        ])
    output.seek(0)
    return output.getvalue()


@router.post("/rapprochement-bancaire/batches/{batch_id}/sage-lines/export-csv")
def export_bank_reconciliation_sage_csv(
    batch_id: int,
    payload: BankReconciliationSageGenerationRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    generated = generate_sage_lines(batch_id, payload)
    lines: List[BankReconciliationSageLine] = generated["lines"]

    content = _build_sage_csv(lines)
    filename = f"saisie_banque_sage_{date.today():%Y%m%d}.csv"

    log_audit_action(
        user=user,
        action="export",
        module="rapprochement_bancaire",
        entity_type="bank_reconciliation_batch",
        entity_id=str(batch_id),
        detail={"filename": filename, "lines": len(lines)},
        request=request,
    )

    return {
        "filename": filename,
        "content": content,
    }


@router.post(
    "/rapprochement-bancaire/batches/{batch_id}/sage-lines/save",
    response_model=BankReconciliationSageSaveResponse,
)
def save_sage_lines(
    batch_id: int,
    payload: BankReconciliationSageGenerationRequest,
):
    generated = generate_sage_lines(batch_id, payload)
    lines: List[BankReconciliationSageLine] = generated["lines"]

    with db.get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM bank_reconciliation_sage_lines WHERE batch_id = %s",
            (batch_id,),
        )

        cursor.executemany(
            """
            INSERT INTO bank_reconciliation_sage_lines
            (batch_id, movement_id, line_no, societe, journal, date_ecriture, compte, tiers, debit, credit,
             section_analytique, numero_piece, libelle, devise, type_piece)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    batch_id,
                    line.movement_id,
                    line.line_no,
                    line.societe,
                    line.journal,
                    line.date_ecriture,
                    line.compte,
                    line.tiers,
                    line.debit,
                    line.credit,
                    line.section_analytique,
                    line.numero_piece,
                    line.libelle,
                    line.devise,
                    line.type_piece,
                )
                for line in lines
            ],
        )

        cursor.execute(
            "UPDATE bank_reconciliation_batches SET status = 'sage_saved' WHERE id = %s",
            (batch_id,),
        )

    return {
        "batch_id": batch_id,
        "saved_count": len(lines),
    }