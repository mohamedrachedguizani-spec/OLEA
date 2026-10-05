import os
import tempfile
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, StreamingResponse

from modules.balance.controle import TypeGrandLivreInvalide
from modules.balance.export import build_pdf, build_print_html, build_sections, rapport_fournisseurs
from .service import parser_pdf_fournisseur
from .models import BalanceExportFournisseurs, BalanceFournisseurResponse
from modules.auth.dependencies import require_permission_code

router = APIRouter(prefix="/balance-fournisseur", tags=["Balance Fournisseur"])

MAX_SIZE = 20 * 1024 * 1024  # 20 Mo


@router.post("/agee/parse", response_model=BalanceFournisseurResponse)
async def parse_balance_agee_fournisseur(
    file: UploadFile = File(..., description="Grand Livre Auxiliaire Fournisseurs Sage (PDF)"),
    date_reference: Optional[str] = Form(None, description="YYYY-MM-DD (défaut : fin de période du PDF)"),
    delai_paiement: int = Form(0, ge=0, le=365, description="Délai de paiement en jours"),
    current_user: dict = Depends(require_permission_code("balance_fournisseur.read")),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés.")

    date_ref = None
    if date_reference:
        try:
            date_ref = datetime.strptime(date_reference, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="date_reference invalide (format attendu : YYYY-MM-DD).")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 20 Mo).")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Le fichier n'est pas un PDF valide.")

    temp_filename = os.path.join(tempfile.gettempdir(), f"balance_frs_temp_{uuid.uuid4().hex}.pdf")
    try:
        with open(temp_filename, "wb") as buffer:
            buffer.write(content)

        # pdfplumber est bloquant : on l'exécute hors de la boucle asyncio
        result = await run_in_threadpool(parser_pdf_fournisseur, temp_filename, date_ref, delai_paiement)

        if result.nb_fournisseurs == 0:
            raise HTTPException(
                status_code=422,
                detail="Aucun fournisseur avec un solde non nul trouvé. Vérifiez qu'il s'agit bien du Grand Livre auxiliaire fournisseur Sage (comptes 401/408/409).",
            )
        return result

    except HTTPException:
        raise
    except TypeGrandLivreInvalide as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du parsing : {str(e)}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

@router.post("/agee/export-pdf")
def export_pdf(
    payload: BalanceExportFournisseurs,
    current_user: dict = Depends(require_permission_code("balance_fournisseur.export_pdf")),
):
    """PDF de la balance âgée (charte OLEA, comme les exports Reporting / Rapprochement)."""
    try:
        output = build_pdf(rapport_fournisseurs(payload.analyse, payload.fichier, payload.inclure_detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du PDF : {str(e)}")
    filename = f"Balance_Agee_Fournisseurs_{payload.analyse.date_reference}.pdf"
    return StreamingResponse(output, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/agee/print-html", response_class=HTMLResponse)
def print_html(
    payload: BalanceExportFournisseurs,
    current_user: dict = Depends(require_permission_code("balance_fournisseur.print")),
):
    """Version HTML mise en page pour l'impression navigateur (ouverte dans une nouvelle fenêtre)."""
    try:
        return HTMLResponse(build_print_html(rapport_fournisseurs(payload.analyse, payload.fichier, payload.inclure_detail)))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la préparation de l'impression : {str(e)}")


@router.post("/agee/preview-sections")
def preview_sections(
    payload: BalanceExportFournisseurs,
    current_user: dict = Depends(require_permission_code("balance_fournisseur.read")),
):
    """Contenu du document à imprimer / exporter, pour la prévisualisation avant confirmation."""
    try:
        return build_sections(rapport_fournisseurs(payload.analyse, payload.fichier, payload.inclure_detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la prévisualisation : {str(e)}")