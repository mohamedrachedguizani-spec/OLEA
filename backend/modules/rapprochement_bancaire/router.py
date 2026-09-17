import os
import json
import math
from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from modules.auth.dependencies import require_permission_code
from modules.audit.service import log_audit_action
from modules.notifications.service import notify_module_users
from modules.notifications.rules import has_important_reconciliation_discrepancy
from database import db
from modules.rapprochement_bancaire.models import (
    ReconciliationOptions,
    ReconciliationContext,
    ReconciliationPdfRequest,
    ReconciliationResult,
    ReconciliationHistoryResponse,
)
from modules.rapprochement_bancaire.pdf_export import build_reconciliation_pdf
from modules.rapprochement_bancaire.constants import BANK_JOURNAL_ACCOUNTS
from modules.rapprochement_bancaire.service import (
    extract_bank_opening_balance,
    extract_sage_opening_balance,
    parse_sage_file,
    parse_bank_file,
    reconcile,
    calculate_reconciliation_balances,
)

router = APIRouter(
    tags=["Rapprochement Bancaire"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[],
)


@router.get("/rapprochement/bank-accounts")
def get_bank_accounts(
    _user: dict = Depends(require_permission_code("rapprochement_bancaire.run")),
):
    return [
        {"journal": journal, "account_code": account_code}
        for journal, account_code in BANK_JOURNAL_ACCOUNTS.items()
    ]

@router.post("/rapprochement/compare", response_model=ReconciliationResult)
def compare_files(
    request: Request,
    sage_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
    bank_journal: str = Form(...),
    period: str = Form(...),
    user: dict = Depends(require_permission_code("rapprochement_bancaire.run")),
):
    """
    Téléverse et compare les écritures du Grand Livre Sage et les mouvements du relevé bancaire.
    """
    if not sage_file.filename or not bank_file.filename:
        raise HTTPException(status_code=400, detail="Les deux fichiers doivent être fournis.")

    normalized_journal = bank_journal.strip().upper()
    account_code = BANK_JOURNAL_ACCOUNTS.get(normalized_journal)
    if not account_code:
        raise HTTPException(status_code=400, detail="Compte bancaire (journal) invalide.")
    try:
        year_text, month_text = period.split("-", 1)
        year, month = int(year_text), int(month_text)
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="La période doit être renseignée au format AAAA-MM.")

    # Lire le fichier Sage
    sage_bytes = sage_file.file.read()
    if not sage_bytes:
        raise HTTPException(status_code=400, detail="Le fichier Sage est vide.")

    # Lire le relevé bancaire
    bank_bytes = bank_file.file.read()
    if not bank_bytes:
        raise HTTPException(status_code=400, detail="Le relevé bancaire est vide.")

    sage_opening = extract_sage_opening_balance(sage_bytes, sage_file.filename)
    bank_opening = extract_bank_opening_balance(
        bank_bytes, bank_file.filename, bank_file.content_type or ""
    )

    # Le compte et la période décrivent le rapprochement, sans réduire les
    # mouvements effectivement présents dans les deux fichiers importés.
    sage_movements = parse_sage_file(sage_bytes, sage_file.filename)
    bank_movements = parse_bank_file(
        bank_bytes,
        bank_file.filename,
        bank_file.content_type or ""
    )
    if not sage_movements:
        raise HTTPException(
            status_code=400,
            detail="Aucune écriture SAGE exploitable n'a été trouvée dans le fichier importé.",
        )
    if not bank_movements:
        raise HTTPException(
            status_code=400,
            detail="Aucun mouvement bancaire exploitable n'a été trouvé dans le relevé importé.",
        )

    # Configurer les options par défaut
    options = ReconciliationOptions(
        date_tolerance_days=3,
        match_on_label=False,
        match_on_date=False
    )

    # Exécuter le rapprochement
    result = reconcile(bank_movements, sage_movements, options)
    opening_difference = None
    opening_status = "unverifiable"
    if sage_opening.amount is not None and bank_opening.amount is not None:
        opening_difference = round(bank_opening.amount - sage_opening.amount, 3)
        opening_status = "conforme" if abs(opening_difference) <= 0.01 else "ecart"
    balance_control = calculate_reconciliation_balances(
        result, sage_opening.amount, bank_opening.amount
    )
    result.context = ReconciliationContext(
        bank_journal=normalized_journal,
        account_code=account_code,
        sage_filename=sage_file.filename,
        bank_filename=bank_file.filename,
        period=period,
        period_start=period_start,
        period_end=period_end,
        sage_opening=sage_opening,
        bank_opening=bank_opening,
        opening_difference=opening_difference,
        opening_status=opening_status,
        **balance_control,
    )

    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO bank_reconciliation_results "
            "(sage_file_name, bank_file_name, compte_banque, compte_comptable, periode, result_json, "
            "total_bank_movements, total_sage_movements, auto_reconciled_count, discrepancies_count, "
            "total_discrepancy_amount, automation_rate, opening_status, created_by_user_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                sage_file.filename,
                bank_file.filename,
                normalized_journal,
                account_code,
                period_start,
                result.model_dump_json() if hasattr(result, "model_dump_json") else result.json(),
                result.stats.total_bank_movements,
                result.stats.total_sage_movements,
                result.stats.auto_reconciled_count,
                result.stats.discrepancies_count,
                result.stats.total_discrepancy_amount,
                result.stats.automation_rate,
                opening_status,
                user["id"],
            ),
        )
        reconciliation_id = int(cursor.lastrowid)
    result.id = reconciliation_id

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
            "bank_journal": normalized_journal,
            "account_code": account_code,
            "period": period,
            "opening_status": opening_status,
            "opening_difference": opening_difference,
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
                "bank_journal": normalized_journal,
                "period": period,
            },
            entity_type="bank_reconciliation",
            entity_id=str(reconciliation_id),
            route=f"/rapprochement-bancaire?result={reconciliation_id}&view=discrepancies",
        )

    return result


@router.get("/rapprochement/results", response_model=ReconciliationHistoryResponse)
def list_reconciliation_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    journal: str | None = Query(None),
    period: str | None = Query(None),
    search: str | None = Query(None),
    _user: dict = Depends(require_permission_code("rapprochement_bancaire.run")),
):
    """Liste paginée des rapprochements réalisés, avec synthèse et auteur."""
    clauses = []
    params = []
    if journal:
        clauses.append("r.compte_banque = %s")
        params.append(journal.strip().upper())
    if period:
        try:
            year, month = (int(part) for part in period.split("-", 1))
            period_start = date(year, month, 1)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="La période doit être au format AAAA-MM.")
        clauses.append("r.periode = %s")
        params.append(period_start)
    if search:
        like = f"%{search.strip()}%"
        clauses.append(
            "(r.sage_file_name LIKE %s OR r.bank_file_name LIKE %s OR "
            "r.compte_banque LIKE %s OR r.compte_comptable LIKE %s OR "
            "u.username LIKE %s OR u.full_name LIKE %s)"
        )
        params.extend([like] * 6)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * page_size
    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM bank_reconciliation_results r "
            f"LEFT JOIN users u ON u.id = r.created_by_user_id {where}",
            tuple(params),
        )
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            "SELECT r.*, COALESCE(NULLIF(u.full_name, ''), u.username) AS created_by "
            "FROM bank_reconciliation_results r "
            f"LEFT JOIN users u ON u.id = r.created_by_user_id {where} "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s",
            tuple([*params, page_size, offset]),
        )
        rows = cursor.fetchall()

    items = []
    for row in rows:
        raw = row.get("result_json")
        stored = json.loads(raw) if isinstance(raw, str) else (raw or {})
        stats = stored.get("stats") or {}
        context = stored.get("context") or {}
        period_value = row.get("periode")
        items.append({
            "id": row["id"],
            "bank_journal": row.get("compte_banque") or context.get("bank_journal"),
            "account_code": row.get("compte_comptable") or context.get("account_code"),
            "period": period_value.strftime("%Y-%m") if period_value else context.get("period"),
            "sage_filename": row.get("sage_file_name") or context.get("sage_filename"),
            "bank_filename": row.get("bank_file_name") or context.get("bank_filename"),
            "total_bank_movements": row.get("total_bank_movements") if row.get("total_bank_movements") is not None else stats.get("total_bank_movements", 0),
            "total_sage_movements": row.get("total_sage_movements") if row.get("total_sage_movements") is not None else stats.get("total_sage_movements", 0),
            "auto_reconciled_count": row.get("auto_reconciled_count") if row.get("auto_reconciled_count") is not None else stats.get("auto_reconciled_count", 0),
            "discrepancies_count": row.get("discrepancies_count") if row.get("discrepancies_count") is not None else stats.get("discrepancies_count", 0),
            "total_discrepancy_amount": float(row.get("total_discrepancy_amount") if row.get("total_discrepancy_amount") is not None else stats.get("total_discrepancy_amount", 0)),
            "automation_rate": float(row.get("automation_rate") if row.get("automation_rate") is not None else stats.get("automation_rate", 0)),
            "opening_status": row.get("opening_status") or context.get("opening_status"),
            "created_by": row.get("created_by"),
            "created_at": row["created_at"],
        })
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


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
    result = json.loads(payload) if isinstance(payload, str) else payload
    result["id"] = result_id
    return result


@router.delete("/rapprochement/results/{result_id}")
def delete_reconciliation_result(
    result_id: int,
    request: Request,
    user: dict = Depends(require_permission_code("rapprochement_bancaire.run")),
):
    """Supprime uniquement un résultat historisé de rapprochement."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT sage_file_name, bank_file_name, compte_banque, compte_comptable, periode "
            "FROM bank_reconciliation_results WHERE id = %s",
            (result_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Résultat de rapprochement introuvable")
        cursor.execute("DELETE FROM bank_reconciliation_results WHERE id = %s", (result_id,))

    log_audit_action(
        user=user,
        action="delete_result",
        module="rapprochement_bancaire",
        entity_type="reconciliation",
        entity_id=str(result_id),
        detail={
            "sage_file": row.get("sage_file_name"),
            "bank_file": row.get("bank_file_name"),
            "bank_journal": row.get("compte_banque"),
            "account_code": row.get("compte_comptable"),
            "period": str(row.get("periode") or ""),
        },
        request=request,
    )
    return {"message": "Le rapprochement a été supprimé de l’historique."}


@router.post("/rapprochement/export-pdf")
def export_reconciliation_pdf(
    payload: ReconciliationPdfRequest,
    request: Request,
    user: dict = Depends(require_permission_code("rapprochement_bancaire.export_pdf")),
):
    """Génère un rapport PDF complet à partir des résultats affichés."""
    pdf_buffer = build_reconciliation_pdf(payload)
    context = payload.result.context
    suffix = f"_{context.bank_journal}_{context.period}" if context else ""
    filename = f"rapprochement_bancaire{suffix}.pdf"

    log_audit_action(
        user=user,
        action="export_pdf",
        module="rapprochement_bancaire",
        entity_type="reconciliation",
        entity_id="reconciliation_pdf",
        detail={
            "sage_file": payload.sage_filename,
            "bank_file": payload.bank_filename,
            "bank_journal": context.bank_journal if context else None,
            "period": context.period if context else None,
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
