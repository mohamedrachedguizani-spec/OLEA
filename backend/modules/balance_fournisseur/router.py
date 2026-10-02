import os
import tempfile
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool

from .service import parser_pdf_fournisseur
from .models import BalanceFournisseurResponse
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du parsing : {str(e)}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)