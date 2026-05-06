from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Depends, Request

from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user, restrict_superadmin
from modules.audit.service import log_audit_action
from .engine import (
    generate_forecast,
    get_annual_comparison,
    get_catalog_items,
    get_comparison,
    get_cycle_status,
    get_subagregats,
    get_year_values,
    import_historical_csv,
    run_cycle_adjustment,
    set_manual_annual_forecast_values,
    set_manual_forecast_values,
    sync_closed_years_into_history,
)
from database import db
from .models import (
    ForecastAnnualComparisonResponse,
    ForecastAnnualComparisonRow,
    ForecastCatalogResponse,
    ForecastComparisonResponse,
    ForecastComparisonRow,
    ForecastCycleRunResponse,
    ForecastCycleStatusResponse,
    ForecastManualAnnualAggregateUpdateRequest,
    ForecastManualAnnualAggregateUpdateResponse,
    ForecastManualAggregateUpdateRequest,
    ForecastManualAggregateUpdateResponse,
    ForecastRunResponse,
    ForecastSubAggregateItem,
    ForecastSubAggregatesResponse,
    HistoricalImportResponse,
    ForecastYearValues,
)

router = APIRouter(
    prefix="/forecast",
    tags=["Forecast Budget BFC"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("forecast"))],
)


@router.post("/historical/import", response_model=HistoricalImportResponse)
def import_historical_data(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Importe l'historique local CSV (2024/2025) vers la base pour l'entraînement forecast.
    """
    base = Path(__file__).resolve().parents[2]
    file_2024 = base / "budget_2024_cloture.csv"
    file_2025 = base / "budget_2025_cloture.csv"
    files = [str(file_2024), str(file_2025)]

    try:
        rows_written, years = import_historical_csv(files)
        log_audit_action(
            user=user,
            action="import_historical",
            module="forecast",
            entity_type="forecast_history",
            entity_id=None,
            detail={"files": files, "rows_written": rows_written, "years": years},
            request=request,
        )
        return HistoricalImportResponse(files=files, rows_written=rows_written, years=years)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur import historique: {str(e)}")


@router.post("/historical/sync-closed")
def sync_closed_historical(
    before_year: int = Query(..., ge=2000, le=2100),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """
    Synchronise les années clôturées (12 mois réels dans sage_bfc_monthly)
    vers bfc_budget_history.
    """
    try:
        payload = sync_closed_years_into_history(before_year=before_year)
        log_audit_action(
            user=user,
            action="sync_closed",
            module="forecast",
            entity_type="forecast_history",
            entity_id=str(before_year),
            detail={"before_year": before_year},
            request=request,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur sync clôture historique: {str(e)}")


@router.get("/historical/years")
def get_historical_years():
    """
    Vérification des années réellement disponibles pour entraînement forecast.
    """
    with db.get_cursor() as cursor:
        cursor.execute("SELECT DISTINCT year FROM bfc_budget_history ORDER BY year ASC")
        years = [int(r["year"]) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT YEAR(periode) AS year, COUNT(DISTINCT MONTH(periode)) AS months
            FROM sage_bfc_monthly
            GROUP BY YEAR(periode)
            ORDER BY YEAR(periode) ASC
            """
        )
        monthly = [{"year": int(r["year"]), "months": int(r["months"])} for r in cursor.fetchall()]

    return {
        "history_years": years,
        "sage_bfc_monthly_years": monthly,
    }


@router.post("/generate", response_model=ForecastRunResponse)
def generate_budget_forecast(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL", description="INITIAL, M03, M06, M08 ou custom"),
    cycle_month: int | None = Query(None, ge=1, le=12),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """
    Génère le budget prévisionnel pour tous les agrégats BFC.
    - cycle INITIAL: budget initial annuel
    - cycle M03/M06/M08: ajustement après clôture cycle
    """
    try:
        run_id, rows_written = generate_forecast(
            target_year=target_year,
            cycle_code=cycle_code,
            cycle_month=cycle_month,
        )
        ws_manager.broadcast(
            "forecast",
            "generated",
            {"target_year": target_year, "cycle_code": cycle_code, "cycle_month": cycle_month, "run_id": run_id},
        )
        log_audit_action(
            user=user,
            action="generate",
            module="forecast",
            entity_type="forecast_run",
            entity_id=str(run_id),
            detail={"target_year": target_year, "cycle_code": cycle_code, "cycle_month": cycle_month},
            request=request,
        )
        return ForecastRunResponse(
            run_id=run_id,
            target_year=target_year,
            cycle_code=cycle_code,
            cycle_month=cycle_month,
            rows_written=rows_written,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur génération forecast: {str(e)}")


@router.get("/catalog", response_model=ForecastCatalogResponse)
def get_forecast_catalog():
    return ForecastCatalogResponse(items=get_catalog_items())


@router.get("/comparison", response_model=ForecastComparisonResponse)
def get_forecast_comparison(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
    month: int = Query(..., ge=1, le=12),
):
    rows = get_comparison(target_year=target_year, cycle_code=cycle_code, month=month)
    mapped = [ForecastComparisonRow(**r) for r in rows]
    return ForecastComparisonResponse(
        target_year=target_year,
        cycle_code=cycle_code,
        mois=month,
        rows=mapped,
    )


@router.get("/annual-comparison", response_model=ForecastAnnualComparisonResponse)
def get_forecast_annual_comparison(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
):
    payload = get_annual_comparison(target_year=target_year, cycle_code=cycle_code)
    mapped_rows = [ForecastAnnualComparisonRow(**r) for r in payload.get("rows", [])]
    return ForecastAnnualComparisonResponse(
        target_year=payload["target_year"],
        cycle_code=payload["cycle_code"],
        cycle_phase=payload["cycle_phase"],
        uploaded_months=payload["uploaded_months"],
        cycle_cutoff_month=payload.get("cycle_cutoff_month"),
        rows=mapped_rows,
    )


@router.get("/subagregats", response_model=ForecastSubAggregatesResponse)
def get_forecast_subagregats(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
    agregat_key: str = Query(...),
    month: int | None = Query(None, ge=1, le=12),
):
    payload = get_subagregats(
        target_year=target_year,
        cycle_code=cycle_code,
        agregat_key=agregat_key,
        month=month,
    )
    return ForecastSubAggregatesResponse(
        target_year=payload["target_year"],
        cycle_code=payload["cycle_code"],
        agregat_key=payload["agregat_key"],
        month=payload.get("month"),
        aggregate_forecast_value=payload.get("aggregate_forecast_value"),
        items=[ForecastSubAggregateItem(**x) for x in payload.get("items", [])],
    )


@router.put("/manual/aggregate", response_model=ForecastManualAggregateUpdateResponse)
def update_manual_aggregate_forecast(
    payload: ForecastManualAggregateUpdateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    try:
        result = set_manual_forecast_values(
            target_year=payload.target_year,
            cycle_code=payload.cycle_code,
            agregat_key=payload.agregat_key,
            month=payload.month,
            forecast_value=payload.forecast_value,
            subagregats=[x.model_dump() for x in payload.subagregats],
        )
        ws_manager.broadcast("forecast", "manual_updated", result)
        log_audit_action(
            user=user,
            action="manual_update",
            module="forecast",
            entity_type="aggregate",
            entity_id=str(payload.agregat_key),
            detail={"target_year": payload.target_year, "month": payload.month},
            request=request,
        )
        return ForecastManualAggregateUpdateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur mise à jour manuelle: {str(e)}")


@router.put("/manual/aggregate-annual", response_model=ForecastManualAnnualAggregateUpdateResponse)
def update_manual_aggregate_forecast_annual(
    payload: ForecastManualAnnualAggregateUpdateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    try:
        result = set_manual_annual_forecast_values(
            target_year=payload.target_year,
            cycle_code=payload.cycle_code,
            agregat_key=payload.agregat_key,
            forecast_annual_value=payload.forecast_annual_value,
            subagregats=[x.model_dump() for x in payload.subagregats],
        )
        ws_manager.broadcast("forecast", "manual_annual_updated", result)
        log_audit_action(
            user=user,
            action="manual_update_annual",
            module="forecast",
            entity_type="aggregate",
            entity_id=str(payload.agregat_key),
            detail={"target_year": payload.target_year},
            request=request,
        )
        return ForecastManualAnnualAggregateUpdateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur mise à jour manuelle annuelle: {str(e)}")


@router.get("/year-values", response_model=ForecastYearValues)
def get_forecast_year_values(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
    agregat_key: str = Query(...),
):
    try:
        payload = get_year_values(target_year=target_year, cycle_code=cycle_code, agregat_key=agregat_key)
        return ForecastYearValues(**payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture série annuelle: {str(e)}")


@router.get("/cycles/status", response_model=ForecastCycleStatusResponse)
def get_adjustment_cycles_status(
    target_year: int = Query(..., ge=2000, le=2100),
):
    """
    Statut des cycles M03/M06/M08 pour activer/désactiver les boutons d'ajustement.
    """
    try:
        payload = get_cycle_status(target_year=target_year)
        return ForecastCycleStatusResponse(**payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut cycles: {str(e)}")


@router.post("/cycles/run", response_model=ForecastCycleRunResponse)
def run_adjustment_cycle(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query(..., description="M03, M06 ou M08"),
    force: bool = Query(False, description="Force l'exécution même si cycle non prêt"),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """
    Déclenche l'ajustement de prévision d'un cycle (bouton fin de cycle).
    """
    try:
        payload = run_cycle_adjustment(target_year=target_year, cycle_code=cycle_code, force=force)
        ws_manager.broadcast("forecast", "cycle_run", payload)
        log_audit_action(
            user=user,
            action="run_cycle",
            module="forecast",
            entity_type="cycle",
            entity_id=str(cycle_code),
            detail={"target_year": target_year, "force": force},
            request=request,
        )
        return ForecastCycleRunResponse(**payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur exécution cycle: {str(e)}")
