import io
import json
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from database import db
from ws_manager import manager as ws_manager
from .config import get_mapping_config
from .mapper import SageBFCMapper
from .parser import SageBalanceParser
from .models import (
    TableauBFCResponse, 
    MappingStats, 
    ParseRequest,
    MonthlyDataSummary,
    MonthlyDataFull
)

router = APIRouter(
    prefix="/sage-bfc",
    tags=["SAGE → BFC Parser"],
    responses={404: {"description": "Non trouvé"}}
)

# Stockage temporaire des tableaux générés (en production, utiliser Redis/DB)
_tableaux_cache = {}

def get_mapper():
    """Dependency pour obtenir le mapper"""
    config = get_mapping_config()
    return SageBFCMapper(config)

def get_parser(mapper: SageBFCMapper = Depends(get_mapper)):
    """Dependency pour obtenir le parser"""
    return SageBalanceParser(mapper)

@router.get("/mapping/stats", response_model=MappingStats)
async def get_mapping_stats(mapper: SageBFCMapper = Depends(get_mapper)):
    """
    Récupère les statistiques du mapping SAGE → BFC
    """
    stats = mapper.get_stats()
    return MappingStats(**stats)

@router.post("/parse", response_model=TableauBFCResponse)
async def parse_balance(
    file: UploadFile = File(..., description="Fichier balance SAGE (Excel ou CSV)"),
    periode: str = Query(..., description="Période comptable (YYYY-MM ou YYYY-MM-DD)"),
    parser: SageBalanceParser = Depends(get_parser)
):
    """
    Parse un fichier balance SAGE et retourne le tableau BFC.
    La période comptable est obligatoire (format YYYY-MM ou YYYY-MM-DD).
    Les résultats sont automatiquement sauvegardés en base de données.
    """
    # Convertir la période string en date
    try:
        if len(periode) == 7:  # Format YYYY-MM
            periode_date = date.fromisoformat(periode + "-01")
        else:  # Format YYYY-MM-DD
            periode_date = date.fromisoformat(periode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format de période invalide: {periode}. Utilisez YYYY-MM ou YYYY-MM-DD")
    # Vérification extension
    allowed_extensions = ['.xlsx', '.xls', '.csv']
    file_ext = file.filename.lower().split('.')[-1]
    if f'.{file_ext}' not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Format non supporté. Formats acceptés: {', '.join(allowed_extensions)}"
        )
    
    try:
        content = await file.read()
        
        # Parsing avec la période obligatoire
        resultat = parser.parse_file(
            file_content=content,
            filename=file.filename,
            periode=periode_date
        )
        
        # Stockage en cache pour export ultérieur
        tableau_id = str(uuid.uuid4())
        _tableaux_cache[tableau_id] = resultat
        
        # Sauvegarde automatique en base de données
        _save_monthly_data(resultat, file.filename)

        ws_manager.broadcast("sage_bfc", "upload", {"periode": str(resultat.periode)})

        return resultat
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traitement: {str(e)}")

@router.get("/tableau/{tableau_id}", response_model=TableauBFCResponse)
async def get_tableau(tableau_id: str):
    """
    Récupère un tableau BFC précédemment généré (stocké en cache)
    """
    if tableau_id not in _tableaux_cache:
        raise HTTPException(status_code=404, detail="Tableau non trouvé ou expiré")
    
    return _tableaux_cache[tableau_id]

@router.get("/tableau/{tableau_id}/export/excel")
async def export_excel(tableau_id: str):
    """
    Exporte un tableau BFC au format Excel
    """
    if tableau_id not in _tableaux_cache:
        raise HTTPException(status_code=404, detail="Tableau non trouvé ou expiré")
    
    tableau = _tableaux_cache[tableau_id]
    
    try:
        import pandas as pd
        
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Formats
            money_format = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
            header_format = workbook.add_format({
                'bold': True, 'bg_color': '#4472C4', 
                'font_color': 'white', 'border': 1
            })
            
            # Feuille 1: Détail des lignes
            df_detail = pd.DataFrame([l.dict() for l in tableau.lignes])
            df_detail.to_excel(writer, sheet_name='Lignes BFC', index=False)
            worksheet1 = writer.sheets['Lignes BFC']
            worksheet1.set_column('E:F', 15, money_format)
            
            # Feuille 2: Résumé P&L
            resume_data = {
                'Ligne': [
                    'CA BRUT', 'Rétrocessions', 'CA NET',
                    'Autres Produits', 'TOTAL PRODUITS',
                    '', 'Frais Personnel', 'Honoraires', 'Frais Commerciaux',
                    'Impôts', 'Fonctionnement', 'Autres Charges',
                    'Brand Fees', 'Management Fees', 'TOTAL CHARGES',
                    '', 'EBITDA', 'EBITDA %',
                    'Produits Financiers', 'Charges Financières', 'Résultat Financier',
                    'Dotations', 'Résultat avant Impôt', 'Impôt', 'RÉSULTAT NET', 'RN %'
                ],
                'Montant (TND)': [
                    tableau.resume.ca_brut, tableau.resume.retrocessions, tableau.resume.ca_net,
                    tableau.resume.autres_produits, tableau.resume.total_produits,
                    '',
                    tableau.resume.frais_personnel, tableau.resume.honoraires,
                    tableau.resume.frais_commerciaux, tableau.resume.impots_taxes,
                    tableau.resume.fonctionnement, tableau.resume.autres_charges,
                    tableau.resume.brand_fees, tableau.resume.management_fees,
                    tableau.resume.total_charges,
                    '',
                    tableau.resume.ebitda, f"{tableau.resume.ebitda_pct:.2f}%",
                    tableau.resume.produits_financiers, tableau.resume.charges_financieres,
                    tableau.resume.resultat_financier,
                    tableau.resume.dotations, tableau.resume.resultat_avant_impot,
                    tableau.resume.impot_societes, tableau.resume.resultat_net,
                    f"{tableau.resume.resultat_net_pct:.2f}%"
                ]
            }
            df_resume = pd.DataFrame(resume_data)
            df_resume.to_excel(writer, sheet_name='Résumé P&L', index=False)
            worksheet2 = writer.sheets['Résumé P&L']
            worksheet2.set_column('B:B', 20, money_format)
        
        output.seek(0)
        
        periode_str = tableau.periode.strftime('%Y%m')
        filename = f"BFC_{periode_str}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'export: {str(e)}")


# ===================== Helper: Sauvegarder en BDD =====================

def _serialize_lignes(lignes):
    """Sérialise la liste de lignes BFC en JSON"""
    return json.dumps([l.model_dump(mode='json') if hasattr(l, 'model_dump') else _ligne_to_dict(l) for l in lignes], default=str)

def _ligne_to_dict(ligne):
    """Convertit une LigneBudgetBFC en dict sérialisable"""
    d = ligne.dict() if hasattr(ligne, 'dict') else ligne.__dict__
    # Convertir les Decimal et date en types sérialisables
    result = {}
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        elif hasattr(v, '__float__'):
            result[k] = float(v)
        else:
            result[k] = v
    return result

def _serialize_resume(resume):
    """Sérialise le résumé en JSON"""
    if hasattr(resume, 'model_dump'):
        d = resume.model_dump(mode='json')
    else:
        d = resume.dict() if hasattr(resume, 'dict') else resume.__dict__
        result = {}
        for k, v in d.items():
            if hasattr(v, 'isoformat'):
                result[k] = v.isoformat()
            elif hasattr(v, '__float__'):
                result[k] = float(v)
            else:
                result[k] = v
        d = result
    return json.dumps(d, default=str)

def _save_monthly_data(resultat: TableauBFCResponse, file_name: str):
    """Sauvegarde ou met à jour les données mensuelles en BDD"""
    resume_json = _serialize_resume(resultat.resume)
    lignes_json = _serialize_lignes(resultat.lignes)
    
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO sage_bfc_monthly 
                (periode, resume, lignes, file_name, lignes_count)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                resume = VALUES(resume),
                lignes = VALUES(lignes),
                file_name = VALUES(file_name),
                lignes_count = VALUES(lignes_count),
                updated_at = CURRENT_TIMESTAMP
        """, (
            resultat.periode,
            resume_json,
            lignes_json,
            file_name,
            len(resultat.lignes)
        ))


# ===================== CRUD: Données mensuelles =====================

@router.get("/monthly", response_model=list[MonthlyDataSummary])
async def get_all_monthly():
    """
    Récupère la liste de tous les mois stockés (sans lignes détaillées)
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT periode, file_name, lignes_count, resume, created_at, updated_at
            FROM sage_bfc_monthly
            ORDER BY periode ASC
        """)
        rows = cursor.fetchall()
    
    result = []
    for row in rows:
        resume_data = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
        result.append(MonthlyDataSummary(
            periode=row['periode'],
            file_name=row['file_name'],
            lignes_count=row['lignes_count'],
            resume=resume_data,
            created_at=str(row['created_at']) if row['created_at'] else None,
            updated_at=str(row['updated_at']) if row['updated_at'] else None
        ))
    
    return result


@router.get("/monthly/{periode}", response_model=MonthlyDataFull)
async def get_monthly_detail(periode: str):
    """
    Récupère les données complètes d'un mois (avec lignes, validations, etc.)
    """
    try:
        if len(periode) == 7:
            periode = date.fromisoformat(periode + "-01")
        else:
            periode = date.fromisoformat(periode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format de période invalide: {periode}")
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT periode, file_name, lignes_count, resume, lignes, 
                   created_at, updated_at
            FROM sage_bfc_monthly
            WHERE periode = %s
        """, (periode,))
        row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Aucune donnée pour la période {periode}")
    
    resume_data = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
    lignes_data = row['lignes'] if isinstance(row['lignes'], list) else json.loads(row['lignes'])
    
    return MonthlyDataFull(
        periode=row['periode'],
        file_name=row['file_name'],
        lignes_count=row['lignes_count'],
        resume=resume_data,
        lignes=lignes_data,
        created_at=str(row['created_at']) if row['created_at'] else None,
        updated_at=str(row['updated_at']) if row['updated_at'] else None
    )


@router.delete("/monthly/{periode}")
async def delete_monthly(periode: str):
    """
    Supprime les données d'un mois spécifique
    """
    try:
        if len(periode) == 7:
            periode = date.fromisoformat(periode + "-01")
        else:
            periode = date.fromisoformat(periode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format de période invalide: {periode}")
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id FROM sage_bfc_monthly WHERE periode = %s", (periode,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Aucune donnée pour la période {periode}")
        
        cursor.execute("DELETE FROM sage_bfc_monthly WHERE periode = %s", (periode,))

    ws_manager.broadcast("sage_bfc", "delete", {"periode": str(periode)})

    return {"status": "supprimé", "periode": str(periode)}


@router.delete("/monthly")
async def delete_all_monthly():
    """
    Supprime toutes les données mensuelles
    """
    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as cnt FROM sage_bfc_monthly")
        count = cursor.fetchone()['cnt']
        cursor.execute("DELETE FROM sage_bfc_monthly")

    ws_manager.broadcast("sage_bfc", "delete_all", {"count": count})

    return {"status": "supprimé", "count": count}