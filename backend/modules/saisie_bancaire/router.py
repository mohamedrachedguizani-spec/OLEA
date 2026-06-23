from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from datetime import date, datetime
from typing import List, Optional, Dict
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
    SaveSessionRequest,
    SessionEntry,
    SaveSessionResponse,
    PendingSession,
)


router = APIRouter(
    tags=["Saisie Bancaire"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("saisie_bancaire"))],
)


from .service import (
    _parse_date,
    _parse_csv_text,
    _parse_pdf,
    _extract_movements
)


@router.post("/saisie-bancaire/upload", response_model=BankReconciliationUploadResponse)
def upload_bank_reconciliation(
    request: Request,
    file: UploadFile = File(...),
    periode_debut: Optional[str] = Form(None),
    periode_fin: Optional[str] = Form(None),
    compte_banque: str = Form(...),
    compte_comptable: str = Form(...),
    taux_conversion: Optional[float] = Form(None),
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

    _DEVISE_MAP = {"UB2": "EUR", "UB3": "USD"}
    devise_source = _DEVISE_MAP.get(compte_banque.strip().upper())
    if devise_source and taux_conversion and taux_conversion > 0:
        for m in movements:
            m["debit"] = round(m["debit"] * taux_conversion, 3)
            m["credit"] = round(m["credit"] * taux_conversion, 3)
    elif devise_source and (not taux_conversion or taux_conversion <= 0):
        raise HTTPException(
            status_code=400,
            detail=f"Le compte {compte_banque} est en {devise_source}. Veuillez saisir un taux de conversion valide.",
        )

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bank_reconciliation_batches
            (periode_debut, periode_fin, compte_banque, compte_comptable, file_name, file_type, status, taux_conversion, devise_source, created_by_user_id, created_by_username)
            VALUES (%s, %s, %s, %s, %s, %s, 'extracted', %s, %s, %s, %s)
            """,
            (
                parsed_periode_debut,
                parsed_periode_fin,
                compte_banque.strip(),
                compte_comptable.strip(),
                file_name,
                extension or file_type or "unknown",
                taux_conversion if devise_source else None,
                devise_source,
                user.get("id"),
                user.get("username"),
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
        module="saisie_bancaire",
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


@router.get("/saisie-bancaire/batches/{batch_id}/movements", response_model=List[BankReconciliationMovement])
def get_bank_reconciliation_movements(batch_id: int):
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM bank_reconciliation_movements WHERE batch_id = %s ORDER BY date_operation ASC, id ASC",
            (batch_id,),
        )
        return cursor.fetchall()


@router.get("/saisie-bancaire/batches/{batch_id}", response_model=BankReconciliationBatch)
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
    "/saisie-bancaire/batches/{batch_id}/sage-lines",
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

        line1_tiers = None  # Le tiers est affecté uniquement à la ligne de contrepartie (Ligne 2)
        line1_section = sections_by_movement.get(movement_id) or payload.section_analytique

        # Numéro de pièce : Nom de la banque (compte_banque) - Année
        numero_piece = f"{compte_banque}-{date_ecriture.year}"

        lines.append(
            BankReconciliationSageLine(
                movement_id=movement_id,
                line_no=1,
                societe="TN01",
                journal=compte_banque,
                date_ecriture=date_ecriture,
                compte=compte_comptable,
                tiers=line1_tiers,
                debit=credit,
                credit=debit,
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
                debit=debit,
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


@router.post("/saisie-bancaire/batches/{batch_id}/sage-lines/export-csv")
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
        module="saisie_bancaire",
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
    "/saisie-bancaire/batches/{batch_id}/sage-lines/save",
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


# ===================== Session de saisie =====================


@router.get("/saisie-bancaire/pending-sessions", response_model=List[PendingSession])
def get_pending_sessions(user: dict = Depends(get_current_user)):
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT b.*,
                   (SELECT COUNT(*) FROM bank_reconciliation_movements WHERE batch_id = b.id) AS total_movements,
                   (SELECT COUNT(*) FROM bank_reconciliation_session_entries WHERE batch_id = b.id AND compte IS NOT NULL AND compte != '') AS completed_movements
            FROM bank_reconciliation_batches b
            WHERE b.status IN ('extracted', 'in_progress')
            ORDER BY b.updated_at DESC
            """
        )
        return cursor.fetchall()


@router.post(
    "/saisie-bancaire/batches/{batch_id}/save-session",
    response_model=SaveSessionResponse,
)
def save_session_entries(
    batch_id: int,
    payload: SaveSessionRequest,
    user: dict = Depends(get_current_user),
):
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id FROM bank_reconciliation_batches WHERE id = %s",
            (batch_id,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Batch introuvable")

        saved = 0
        for movement_id, entry in payload.entries.items():
            cursor.execute(
                """
                INSERT INTO bank_reconciliation_session_entries
                (batch_id, movement_id, compte, tiers, section_analytique)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    compte = VALUES(compte),
                    tiers = VALUES(tiers),
                    section_analytique = VALUES(section_analytique)
                """,
                (
                    batch_id,
                    int(movement_id),
                    (entry.compte or "").strip() or None,
                    (entry.tiers or "").strip() or None,
                    (entry.section_analytique or "").strip() or None,
                ),
            )
            saved += 1

        cursor.execute(
            "UPDATE bank_reconciliation_batches SET status = 'in_progress' WHERE id = %s AND status != 'sage_saved'",
            (batch_id,),
        )

    return {"batch_id": batch_id, "saved_count": saved}


@router.get(
    "/saisie-bancaire/batches/{batch_id}/session-entries",
    response_model=List[SessionEntry],
)
def get_session_entries(batch_id: int):
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT movement_id, compte, tiers, section_analytique
            FROM bank_reconciliation_session_entries
            WHERE batch_id = %s
            """,
            (batch_id,),
        )
        return cursor.fetchall()