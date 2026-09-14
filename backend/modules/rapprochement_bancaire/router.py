import os
import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from modules.auth.dependencies import require_permission_code
from modules.audit.service import log_audit_action
from modules.notifications.service import notify_module_users
from modules.notifications.rules import has_important_reconciliation_discrepancy
from database import db
from modules.rapprochement_bancaire.models import (
    ReconciliationOptions,
    ReconciliationPdfRequest,
    ReconciliationResult,
)
from modules.rapprochement_bancaire.pdf_export import build_reconciliation_pdf
from modules.rapprochement_bancaire.service import parse_sage_file, parse_bank_file, reconcile

router = APIRouter(
    tags=["Rapprochement Bancaire"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[],
)

@router.post("/rapprochement/compare", response_model=ReconciliationResult)
def compare_files(
    request: Request,
    sage_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
    user: dict = Depends(require_permission_code("rapprochement_bancaire.run")),
):
    """
    Téléverse et compare les écritures du Grand Livre Sage et les mouvements du relevé bancaire.
    """
    if not sage_file.filename or not bank_file.filename:
        raise HTTPException(status_code=400, detail="Les deux fichiers doivent être fournis.")

    # Lire le fichier Sage
    sage_bytes = sage_file.file.read()
    if not sage_bytes:
        raise HTTPException(status_code=400, detail="Le fichier Sage est vide.")

    # Lire le relevé bancaire
    bank_bytes = bank_file.file.read()
    if not bank_bytes:
        raise HTTPException(status_code=400, detail="Le relevé bancaire est vide.")

    # Parser le fichier Sage
    sage_movements = parse_sage_file(sage_bytes, sage_file.filename)
    
    # Parser le relevé bancaire
    bank_movements = parse_bank_file(
        bank_bytes,
        bank_file.filename,
        bank_file.content_type or ""
    )

    # Configurer les options par défaut
    options = ReconciliationOptions(
        date_tolerance_days=3,
        match_on_label=False,
        match_on_date=False
    )

    # Exécuter le rapprochement
    result = reconcile(bank_movements, sage_movements, options)

    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO bank_reconciliation_results "
            "(sage_file_name, bank_file_name, result_json, created_by_user_id) "
            "VALUES (%s, %s, %s, %s)",
            (
                sage_file.filename,
                bank_file.filename,
                result.model_dump_json() if hasattr(result, "model_dump_json") else result.json(),
                user["id"],
            ),
        )
        reconciliation_id = int(cursor.lastrowid)

    # Enregistrer dans l'audit log
    log_audit_action(
        user=user,
        action="reconcile",
        module="rapprochement_bancaire",
        entity_type="reconciliation",
        entity_id=str(reconciliation_id),
        detail={
            "sage_file": sage_file.filename,
            "bank_file": bank_file.filename,
            "total_bank_movements": result.stats.total_bank_movements,
            "total_sage_movements": result.stats.total_sage_movements,
            "auto_reconciled": result.stats.auto_reconciled_count,
            "discrepancies": result.stats.discrepancies_count,
            "automation_rate": result.stats.automation_rate
        },
        request=request,
    )

    count_threshold = int(os.getenv("RECONCILIATION_ALERT_COUNT", "5"))
    amount_threshold = float(os.getenv("RECONCILIATION_ALERT_AMOUNT", "1000"))
    if has_important_reconciliation_discrepancy(
        result.stats.discrepancies_count,
        result.stats.total_discrepancy_amount,
        count_threshold,
        amount_threshold,
    ):
        notify_module_users(
            module_name="rapprochement_bancaire",
            notif_type="rapprochement_bancaire.ecarts_importants",
            severity="critical",
            title="Écarts importants détectés",
            message=(
                f"{result.stats.discrepancies_count} écart(s), pour un montant total de "
                f"{result.stats.total_discrepancy_amount:.3f} TND."
            ),
            metadata={
                "discrepancies_count": result.stats.discrepancies_count,
                "total_discrepancy_amount": result.stats.total_discrepancy_amount,
                "sage_file": sage_file.filename,
                "bank_file": bank_file.filename,
            },
            entity_type="bank_reconciliation",
            entity_id=str(reconciliation_id),
            route=f"/rapprochement-bancaire?result={reconciliation_id}&view=discrepancies",
        )

    return result


@router.get("/rapprochement/results/{result_id}", response_model=ReconciliationResult)
def get_reconciliation_result(
    result_id: int,
    _user: dict = Depends(require_permission_code("rapprochement_bancaire.run")),
):
    """Recharge un rapprochement ciblé depuis une notification."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT result_json FROM bank_reconciliation_results WHERE id = %s",
            (result_id,),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Résultat de rapprochement introuvable")
    payload = row["result_json"]
    return json.loads(payload) if isinstance(payload, str) else payload


@router.post("/rapprochement/export-pdf")
def export_reconciliation_pdf(
    payload: ReconciliationPdfRequest,
    request: Request,
    user: dict = Depends(require_permission_code("rapprochement_bancaire.export_pdf")),
):
    """Génère un rapport PDF complet à partir des résultats affichés."""
    pdf_buffer = build_reconciliation_pdf(payload)
    filename = "rapprochement_bancaire.pdf"

    log_audit_action(
        user=user,
        action="export_pdf",
        module="rapprochement_bancaire",
        entity_type="reconciliation",
        entity_id="reconciliation_pdf",
        detail={
            "sage_file": payload.sage_filename,
            "bank_file": payload.bank_filename,
            "total_bank_movements": payload.result.stats.total_bank_movements,
            "total_sage_movements": payload.result.stats.total_sage_movements,
            "auto_reconciled": payload.result.stats.auto_reconciled_count,
            "discrepancies": payload.result.stats.discrepancies_count,
        },
        request=request,
    )

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
