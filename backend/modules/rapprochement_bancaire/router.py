from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from modules.auth.dependencies import restrict_superadmin, require_permission
from modules.audit.service import log_audit_action
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
    dependencies=[Depends(restrict_superadmin("rapprochement_bancaire"))],
)

@router.post("/rapprochement/compare", response_model=ReconciliationResult)
def compare_files(
    request: Request,
    sage_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
    user: dict = Depends(require_permission("rapprochement_bancaire", "read")),
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

    # Enregistrer dans l'audit log
    log_audit_action(
        user=user,
        action="reconcile",
        module="rapprochement_bancaire",
        entity_type="reconciliation",
        entity_id=f"rec_{int(request.created_at.timestamp())}" if hasattr(request, "created_at") else "rec_now",
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

    return result


@router.post("/rapprochement/export-pdf")
def export_reconciliation_pdf(
    payload: ReconciliationPdfRequest,
    request: Request,
    user: dict = Depends(require_permission("rapprochement_bancaire", "read")),
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
