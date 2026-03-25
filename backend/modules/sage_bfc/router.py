import io
import json
import uuid
from decimal import Decimal
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from database import db
from ws_manager import manager as ws_manager
from modules.forecast.engine import (
    sync_actuals_from_resume,
    clear_actuals_for_month,
    clear_all_actuals,
    invalidate_adjustment_cycles_for_year,
    purge_all_adjustment_cycles,
)
from .config import get_mapping_config
from .mapper import SageBFCMapper
from .parser import SageBalanceParser
from .models import (
    TableauBFCResponse,
    TableauBFCSummary,
    LigneBudgetBFC,
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

_AGREGAT_ALIASES = {
    # clés internes
    "ca_brut": "ca_brut",
    "retrocessions": "retrocessions",
    "ca_net": "ca_net",
    "autres_produits": "autres_produits",
    "total_produits": "total_produits",
    "frais_personnel": "frais_personnel",
    "honoraires": "honoraires",
    "frais_commerciaux": "frais_commerciaux",
    "impots_taxes": "impots_taxes",
    "fonctionnement": "fonctionnement",
    "autres_charges": "autres_charges",
    "produits_financiers": "produits_financiers",
    "charges_financieres": "charges_financieres",
    "dotations": "dotations",
    "impot_societes": "impot_societes",
    "produits_exceptionnels": "produits_exceptionnels",
    "charges_exceptionnelles": "charges_exceptionnelles",
    "resultat_financier": "resultat_financier",
    "resultat_exceptionnel": "resultat_exceptionnel",
    "resultat_avant_impot": "resultat_avant_impot",
    "resultat_net": "resultat_net",
    # libellés courants
    "ca brut": "ca_brut",
    "retrocessions": "retrocessions",
    "ca net": "ca_net",
    "autres produits exploitation": "autres_produits",
    "frais personnel": "frais_personnel",
    "honoraires sous traitance": "honoraires",
    "frais commerciaux": "frais_commerciaux",
    "impots taxes": "impots_taxes",
    "fonctionnement courant": "fonctionnement",
    "autres charges": "autres_charges",
    "produits financiers": "produits_financiers",
    "charges financieres": "charges_financieres",
    "dotations amortissements": "dotations",
    "impot societes": "impot_societes",
    "produits exceptionnels": "produits_exceptionnels",
    "charges exceptionnelles": "charges_exceptionnelles",
}


def _normalize_agregat_name(value: str) -> str:
    key = " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())
    mapped = _AGREGAT_ALIASES.get(key)
    if not mapped:
        raise HTTPException(
            status_code=400,
            detail=f"Agrégat inconnu: '{value}'. Exemple: ca_brut, frais_personnel, resultat_net"
        )
    return mapped

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
        resultat_cumule = parser.parse_file(
            file_content=content,
            filename=file.filename,
            periode=periode_date
        )

        # Conversion cumulé -> réel mensuel (M réel = M cumulé - M-1 cumulé)
        resultat_reel = _convert_cumulative_to_real(resultat_cumule, parser)
        
        # Stockage en cache pour export ultérieur
        tableau_id = str(uuid.uuid4())
        _tableaux_cache[tableau_id] = resultat_reel
        
        # Sauvegarde automatique en base de données
        _save_monthly_data(resultat_reel, file.filename)
        _save_monthly_cumulative_data(resultat_cumule, file.filename)

        # Synchronisation temps réel des écarts forecast vs réalisé
        resume_payload = (
            resultat_reel.resume.model_dump(mode="json")
            if hasattr(resultat_reel.resume, "model_dump")
            else resultat_reel.resume.dict()
        )
        sync_actuals_from_resume(resultat_reel.periode, resume_payload)

        ws_manager.broadcast("sage_bfc", "upload", {"periode": str(resultat_reel.periode)})
        ws_manager.broadcast(
            "forecast",
            "annual_comparison_updated",
            {"year": resultat_reel.periode.year, "month": resultat_reel.periode.month},
        )

        return resultat_reel
        
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


def _save_monthly_cumulative_data(resultat: TableauBFCResponse, file_name: str):
    """Sauvegarde ou met à jour les données cumulées brutes en BDD"""
    resume_json = _serialize_resume(resultat.resume)
    lignes_json = _serialize_lignes(resultat.lignes)

    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO sage_bfc_monthly_cumule
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


def _build_ligne_key(ligne: LigneBudgetBFC) -> str:
    return "|".join([
        str(ligne.code_sage or ""),
        str(ligne.agregat_bfc or ""),
        str(ligne.sous_categorie or ""),
        str(ligne.type_ligne or ""),
        str(ligne.sens or ""),
    ])


def _group_lignes_by_key(lignes: list[LigneBudgetBFC]) -> dict[str, dict]:
    """
    Regroupe les lignes par clé technique pour éviter les doubles soustractions
    quand plusieurs lignes partagent le même code/aggrégat.
    """
    grouped: dict[str, dict] = {}
    for l in lignes:
        k = _build_ligne_key(l)
        if k not in grouped:
            grouped[k] = {
                "template": l,
                "total": Decimal('0'),
            }
        grouped[k]["total"] += Decimal(str(l.montant))
    return grouped


def _load_previous_cumulative_lignes(periode: date) -> list[LigneBudgetBFC]:
    """
    Charge les lignes cumulées du mois précédent disponible.
    Priorité: table cumulative; fallback: table monthly (rétrocompatibilité).
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT lignes
            FROM sage_bfc_monthly_cumule
            WHERE periode < %s
              AND YEAR(periode) = YEAR(%s)
            ORDER BY periode DESC
            LIMIT 1
        """, (periode, periode))
        row = cursor.fetchone()

    if not row:
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT lignes
                FROM sage_bfc_monthly
                WHERE periode < %s
                  AND YEAR(periode) = YEAR(%s)
                ORDER BY periode DESC
                LIMIT 1
            """, (periode, periode))
            row = cursor.fetchone()

    if not row:
        return []

    raw = row['lignes'] if isinstance(row['lignes'], list) else json.loads(row['lignes'])
    lignes = []
    for item in raw:
        try:
            lignes.append(LigneBudgetBFC(**item))
        except Exception:
            continue
    return lignes


def _convert_cumulative_to_real(resultat_cumule: TableauBFCResponse, parser: SageBalanceParser) -> TableauBFCResponse:
    """Convertit un résultat cumulé en réel mensuel via delta au cumul précédent."""
    previous_lignes = _load_previous_cumulative_lignes(resultat_cumule.periode)
    if not previous_lignes:
        # Premier mois disponible: réel = cumulé
        return resultat_cumule

    previous_grouped = _group_lignes_by_key(previous_lignes)
    current_grouped = _group_lignes_by_key(resultat_cumule.lignes)

    lignes_reelles: list[LigneBudgetBFC] = []
    for k, current_info in current_grouped.items():
        template = current_info["template"]
        current_amount = current_info["total"]
        prev_amount = previous_grouped.get(k, {}).get("total", Decimal('0'))
        real_amount = current_amount - prev_amount

        lignes_reelles.append(
            template.model_copy(update={
                "montant": real_amount,
                "montant_absolu": abs(real_amount),
            })
        )

    agregats = parser.mapper.calculer_agregats(lignes_reelles)
    resume_reel = TableauBFCSummary(
        periode=resultat_cumule.periode,
        ca_brut=float(agregats['ca_brut']),
        retrocessions=float(agregats['retrocessions']),
        ca_net=float(agregats['ca_net']),
        autres_produits=float(agregats['autres_produits']),
        total_produits=float(agregats['total_produits']),
        frais_personnel=float(agregats['frais_personnel']),
        honoraires=float(agregats['honoraires']),
        frais_commerciaux=float(agregats['frais_commerciaux']),
        impots_taxes=float(agregats['impots_taxes']),
        fonctionnement=float(agregats['fonctionnement']),
        autres_charges=float(agregats['autres_charges']),
        brand_fees=float(agregats['brand_fees']),
        management_fees=float(agregats['management_fees']),
        interco_charges=float(agregats['interco_charges']),
        total_charges=float(agregats['total_charges']),
        ebitda=float(agregats['ebitda']),
        ebitda_pct=float(agregats['ebitda_pct']),
        produits_financiers=float(agregats['produits_financiers']),
        charges_financieres=float(agregats['charges_financieres']),
        resultat_financier=float(agregats['resultat_financier']),
        dotations=float(agregats['dotations']),
        produits_exceptionnels=float(agregats['produits_exceptionnels']),
        charges_exceptionnelles=float(agregats['charges_exceptionnelles']),
        resultat_exceptionnel=float(agregats['resultat_exceptionnel']),
        resultat_avant_impot=float(agregats['resultat_avant_impot']),
        impot_societes=float(agregats['impot_societes']),
        resultat_net=float(agregats['resultat_net']),
        resultat_net_pct=float(agregats['resultat_net_pct']),
    )

    return TableauBFCResponse(
        periode=resultat_cumule.periode,
        lignes=lignes_reelles,
        resume=resume_reel,
    )


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
        cursor.execute("DELETE FROM sage_bfc_monthly_cumule WHERE periode = %s", (periode,))

    # Synchroniser le module forecast: suppression des réels/écarts pour ce mois
    clear_actuals_for_month(periode.year, periode.month)

    # Invalider les cycles d'ajustement devenus incohérents (ex: M03 sans 3 mois réels)
    invalidation_payload = invalidate_adjustment_cycles_for_year(periode.year)

    ws_manager.broadcast("sage_bfc", "delete", {"periode": str(periode)})
    ws_manager.broadcast("forecast", "actuals_cleared", {"year": periode.year, "month": periode.month})
    ws_manager.broadcast("forecast", "cycles_invalidated", invalidation_payload)

    return {
        "status": "supprimé",
        "periode": str(periode),
        "forecast_cycle_invalidation": invalidation_payload,
    }


@router.delete("/monthly")
async def delete_all_monthly():
    """
    Supprime toutes les données mensuelles
    """
    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as cnt FROM sage_bfc_monthly")
        count = cursor.fetchone()['cnt']
        cursor.execute("DELETE FROM sage_bfc_monthly")
        cursor.execute("DELETE FROM sage_bfc_monthly_cumule")

    # Synchroniser le module forecast: suppression globale des réels/écarts
    clear_all_actuals()
    purge_payload = purge_all_adjustment_cycles()

    ws_manager.broadcast("sage_bfc", "delete_all", {"count": count})
    ws_manager.broadcast("forecast", "actuals_cleared_all", {"count": count})
    ws_manager.broadcast("forecast", "cycles_purged", purge_payload)

    return {
        "status": "supprimé",
        "count": count,
        "forecast_cycle_purge": purge_payload,
    }


@router.get("/audit/cumulative-delta")
async def get_audit_cumulative_delta(
    year: int = Query(..., ge=2000, le=2100, description="Année fiscale"),
    agregat: str = Query(..., description="Agrégat (ex: ca_brut, frais_personnel, resultat_net)"),
):
    """
    Renvoie la table d'audit comptable mensuelle pour un agrégat:
    - Cn   : cumul courant
    - Cn-1 : cumul précédent (même année)
    - Vn   : valeur mensuelle réelle = Cn - Cn-1
    """
    agregat_key = _normalize_agregat_name(agregat)

    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT MONTH(periode) AS mois, resume
            FROM sage_bfc_monthly_cumule
            WHERE YEAR(periode) = %s
            ORDER BY periode ASC
        """, (year,))
        rows = cursor.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune donnée cumulée trouvée pour l'année {year}."
        )

    table = []
    previous_cumul = Decimal('0')

    for row in rows:
        mois = int(row['mois'])
        resume = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
        current_cumul = Decimal(str(resume.get(agregat_key, 0) or 0))
        valeur_periode = current_cumul - previous_cumul

        table.append({
            "mois": mois,
            "Cn": float(current_cumul),
            "Cn_1": float(previous_cumul),
            "Vn": float(valeur_periode),
            "equation_check": float(previous_cumul + valeur_periode),
            "equation_ok": bool((previous_cumul + valeur_periode) == current_cumul),
        })

        previous_cumul = current_cumul

    return {
        "year": year,
        "agregat": agregat_key,
        "formula": "Cn = Cn-1 + Vn",
        "rows": table,
    }


@router.post("/monthly/recompute-real")
async def recompute_monthly_real_values(mapper: SageBFCMapper = Depends(get_mapper)):
    """
    Recalcule les mois stockés en réel mensuel (delta cumulé M - cumulé M-1)
    à partir des données déjà présentes dans sage_bfc_monthly.
    Utile après migration/activation de la logique cumulée.
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT periode, resume, lignes, file_name, lignes_count
            FROM sage_bfc_monthly
            ORDER BY periode ASC
        """)
        rows = cursor.fetchall()

    if not rows:
        return {"status": "ok", "updated_months": 0, "message": "Aucune donnée à recalculer"}

    prev_cum_by_key: dict[str, Decimal] = {}
    prev_year: Optional[int] = None
    updated = 0

    for row in rows:
        periode = row['periode']
        current_year = int(periode.year)

        # Réinitialisation annuelle: en janvier (ou changement d'année), Cn-1 = 0
        if prev_year is None or current_year != prev_year:
            prev_cum_by_key = {}

        raw_lignes = row['lignes'] if isinstance(row['lignes'], list) else json.loads(row['lignes'])

        cum_lignes: list[LigneBudgetBFC] = []
        for item in raw_lignes:
            try:
                cum_lignes.append(LigneBudgetBFC(**item))
            except Exception:
                continue

        # Sauvegarder le cumul brut pour usage futur
        cum_result = TableauBFCResponse(
            periode=periode,
            lignes=cum_lignes,
            resume=TableauBFCSummary(**(row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])))
        )
        _save_monthly_cumulative_data(cum_result, row.get('file_name'))

        # Calcul réel par delta (sur montants agrégés par clé)
        real_lignes: list[LigneBudgetBFC] = []
        current_grouped = _group_lignes_by_key(cum_lignes)
        current_cum_by_key: dict[str, Decimal] = {}

        for key, info in current_grouped.items():
            template = info["template"]
            current_amount = info["total"]
            current_cum_by_key[key] = current_amount

            prev_amount = prev_cum_by_key.get(key, Decimal('0'))
            real_amount = current_amount - prev_amount
            real_lignes.append(
                template.model_copy(update={
                    "montant": real_amount,
                    "montant_absolu": abs(real_amount),
                })
            )

        agregats = mapper.calculer_agregats(real_lignes)
        resume_reel = TableauBFCSummary(
            periode=periode,
            ca_brut=float(agregats['ca_brut']),
            retrocessions=float(agregats['retrocessions']),
            ca_net=float(agregats['ca_net']),
            autres_produits=float(agregats['autres_produits']),
            total_produits=float(agregats['total_produits']),
            frais_personnel=float(agregats['frais_personnel']),
            honoraires=float(agregats['honoraires']),
            frais_commerciaux=float(agregats['frais_commerciaux']),
            impots_taxes=float(agregats['impots_taxes']),
            fonctionnement=float(agregats['fonctionnement']),
            autres_charges=float(agregats['autres_charges']),
            brand_fees=float(agregats['brand_fees']),
            management_fees=float(agregats['management_fees']),
            interco_charges=float(agregats['interco_charges']),
            total_charges=float(agregats['total_charges']),
            ebitda=float(agregats['ebitda']),
            ebitda_pct=float(agregats['ebitda_pct']),
            produits_financiers=float(agregats['produits_financiers']),
            charges_financieres=float(agregats['charges_financieres']),
            resultat_financier=float(agregats['resultat_financier']),
            dotations=float(agregats['dotations']),
            produits_exceptionnels=float(agregats['produits_exceptionnels']),
            charges_exceptionnelles=float(agregats['charges_exceptionnelles']),
            resultat_exceptionnel=float(agregats['resultat_exceptionnel']),
            resultat_avant_impot=float(agregats['resultat_avant_impot']),
            impot_societes=float(agregats['impot_societes']),
            resultat_net=float(agregats['resultat_net']),
            resultat_net_pct=float(agregats['resultat_net_pct']),
        )

        real_result = TableauBFCResponse(periode=periode, lignes=real_lignes, resume=resume_reel)
        _save_monthly_data(real_result, row.get('file_name'))

        prev_cum_by_key = current_cum_by_key
        prev_year = current_year
        updated += 1

    ws_manager.broadcast("sage_bfc", "recompute_real", {"updated_months": updated})
    ws_manager.broadcast("forecast", "recompute_real", {"updated_months": updated})

    return {"status": "ok", "updated_months": updated}