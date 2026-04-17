import html
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from modules.auth.dependencies import get_current_user, require_permission
from modules.forecast.engine import get_annual_comparison, get_comparison, get_cycle_status, get_subagregats
from .router import (
    _build_annual_forecast_export_rows,
    _build_global_state_df,
    _build_hierarchical_annual_df,
    _build_hierarchical_monthly_detail_df,
    _build_pnl_formatted_hierarchical_df,
    _get_realized_months,
    _normalize_month_param,
    _resolve_detail_months,
    _resolve_pnl_months,
    PNL_KEYS,
)

router = APIRouter(
    prefix="/reporting",
    tags=["Reporting"],
    dependencies=[Depends(get_current_user)],
)


def _fmt_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.3f}".replace(",", " ").replace(".", ",")
    return str(value)


def _row_class(sheet_name: str, row: dict) -> str:
    level = str(row.get("Niveau") or "")
    if sheet_name == "Executive_Summary":
        return "row-kpi"
    if sheet_name in {"Forecast_Annuel_Detail", "Forecast_Mensuel_Detail", "Etat_Globale"}:
        if level == "Agrégat":
            return "row-agg"
        if level == "Sous-agrégat":
            return "row-sub"
    if sheet_name in {"PnL_Formate", "PnL_Formate_Selection", "PnL_Formate_Global"}:
        label = str(row.get("Libellé") or "").lower()
        if any(x in label for x in ["charges", "frais", "impot", "dotations"]):
            return "row-charge"
        if any(x in label for x in ["résultat", "resultat", "ebitda", "profit"]):
            return "row-result"
        return "row-produit"
    return ""


def _table_html(df: pd.DataFrame, sheet_name: str) -> str:
    if df is None or df.empty:
        return '<div class="empty">Aucune donnée</div>'

    cols = list(df.columns)
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body_rows = []
    for row in df.to_dict(orient="records"):
        cls = _row_class(sheet_name, row)
        tds = "".join(f"<td>{html.escape(_fmt_cell(row.get(c)))}</td>" for c in cols)
        body_rows.append(f"<tr class=\"{cls}\">{tds}</tr>")
    body = "".join(body_rows)

    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _build_print_html(title_map: dict[str, str], frames: list[tuple[str, pd.DataFrame]], year: int, cycle_code: str) -> str:
    sections = []
    for sheet_name, df in frames:
        title = title_map.get(sheet_name, sheet_name)
        sections.append(
            f"""
            <section class=\"sheet\">
                <h2>{html.escape(title)}</h2>
                {_table_html(df, sheet_name)}
            </section>
            """
        )

    sections_html = "".join(sections)
    return f"""
<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <title>Impression Reporting {year}</title>
  <style>
    @page {{ size: A4 landscape; margin: 12mm; }}
        * {{
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            forced-color-adjust: none !important;
        }}
        @media print {{
            html, body {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
        }}
    body {{ font-family: Arial, sans-serif; color: #0f172a; }}
    .meta {{ margin-bottom: 14px; font-size: 12px; color: #334155; }}
    .sheet {{ page-break-after: always; }}
    .sheet:last-child {{ page-break-after: auto; }}
    h2 {{ margin: 0 0 10px 0; color: #1E3A8A; font-size: 18px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
    th {{ background: #1E3A8A; color: #fff; border: 1px solid #cbd5e1; padding: 6px; text-align: left; }}
    td {{ border: 1px solid #cbd5e1; padding: 5px; }}
    .row-kpi td {{ background: #EEF2FF; font-weight: 700; }}
    .row-agg td {{ background: #E0F2FE; font-weight: 700; }}
    .row-sub td {{ background: #F8FAFC; }}
    .row-produit td {{ background: #ECFDF5; }}
    .row-charge td {{ background: #FEF2F2; }}
    .row-result td {{ background: #EFF6FF; font-weight: 700; }}
    .empty {{ color: #64748b; font-style: italic; padding: 8px 0; }}
  </style>
</head>
<body>
  
  {sections_html}
</body>
</html>
"""


@router.get("/print/html", response_class=HTMLResponse)
def print_reporting_html(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
    budget_cycle_code: str | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    pnl_scope: str = Query("selected"),
    pnl_months: list[int] | None = Query(None),
    monthly_detail_months: list[int] | None = Query(None),
    include_executive_summary: bool = Query(True),
    include_pnl_formatted: bool = Query(True),
    include_budget_forecast: bool = Query(True),
    include_monthly_forecast: bool = Query(True),
    include_cycles: bool = Query(True),
    include_alerts: bool = Query(False),
    include_subaggregates: bool = Query(True),
    include_global_state: bool = Query(False),
    include_pnl_selected: bool = Query(False),
    include_pnl_global: bool = Query(False),
    _user: dict = Depends(require_permission("reporting", "read")),
):
    try:
        if not any([
            include_executive_summary,
            include_pnl_formatted,
            include_budget_forecast,
            include_cycles,
            include_alerts,
            include_global_state,
        ]):
            if include_pnl_selected or include_pnl_global:
                include_pnl_formatted = True
            else:
                include_global_state = True

        selected_month = _normalize_month_param(target_year, month)
        effective_budget_cycle = budget_cycle_code or cycle_code
        realized_months = _get_realized_months(target_year)

        detail_months = []
        if include_budget_forecast and include_monthly_forecast:
            detail_months = _resolve_detail_months(realized_months, selected_month, monthly_detail_months)

        effective_pnl_months_selected = []
        effective_pnl_months_global = []
        export_pnl_selected = False
        export_pnl_global = False
        if include_pnl_formatted:
            if include_pnl_selected or include_pnl_global:
                export_pnl_selected = include_pnl_selected
                export_pnl_global = include_pnl_global
            else:
                export_pnl_selected = pnl_scope == "selected"
                export_pnl_global = pnl_scope in {"all", "global"}

            if export_pnl_selected:
                effective_pnl_months_selected = _resolve_pnl_months(realized_months, "selected", selected_month, pnl_months)
            if export_pnl_global:
                effective_pnl_months_global = _resolve_pnl_months(realized_months, "global", selected_month, pnl_months)

        annual = get_annual_comparison(target_year=target_year, cycle_code=effective_budget_cycle)
        monthly = get_comparison(target_year=target_year, cycle_code=effective_budget_cycle, month=selected_month)
        cycle_status = get_cycle_status(target_year=target_year)

        annual_raw_rows = annual.get("rows", [])
        annual_df = pd.DataFrame(_build_annual_forecast_export_rows(annual_raw_rows))

        sub_ann_map: dict[str, list[dict]] = {}
        need_annual_sub = include_subaggregates or include_pnl_formatted or include_global_state
        if need_annual_sub:
            for row in annual_raw_rows:
                key = row.get("agregat_key")
                if key:
                    sub_ann_map[key] = list(get_subagregats(target_year, effective_budget_cycle, key, None).get("items", []))

        pnl_selected_df = pd.DataFrame()
        pnl_global_df = pd.DataFrame()
        if include_pnl_formatted:
            annual_base = get_annual_comparison(target_year=target_year, cycle_code=cycle_code)
            annual_pnl_rows = annual_base.get("rows", [])
            pnl_sub_map: dict[str, list[dict]] = {}
            for row in annual_pnl_rows:
                key = row.get("agregat_key")
                if key and key in PNL_KEYS:
                    pnl_sub_map[key] = list(get_subagregats(target_year, cycle_code, key, None).get("items", []))

            if export_pnl_selected:
                pnl_selected_df = _build_pnl_formatted_hierarchical_df(
                    target_year=target_year,
                    cycle_code=cycle_code,
                    annual_rows=annual_pnl_rows,
                    sub_ann_map=pnl_sub_map,
                    pnl_months=effective_pnl_months_selected,
                    pnl_scope="selected",
                )
            if export_pnl_global:
                pnl_global_df = _build_pnl_formatted_hierarchical_df(
                    target_year=target_year,
                    cycle_code=cycle_code,
                    annual_rows=annual_pnl_rows,
                    sub_ann_map=pnl_sub_map,
                    pnl_months=effective_pnl_months_global,
                    pnl_scope="global",
                )

        by_key_annual = {r["agregat_key"]: r for r in annual_raw_rows}
        executive_df = pd.DataFrame([
            {
                "KPI": "CA Net",
                "Prévision Annuelle": by_key_annual.get("ca_net", {}).get("forecast_annual"),
                "Réalisé Cumulé": by_key_annual.get("ca_net", {}).get("actual_total"),
                "Reste budget": by_key_annual.get("ca_net", {}).get("remaining_budget"),
            },
            {
                "KPI": "EBITDA",
                "Prévision Annuelle": by_key_annual.get("ebitda", {}).get("forecast_annual"),
                "Réalisé Cumulé": by_key_annual.get("ebitda", {}).get("actual_total"),
                "Reste budget": by_key_annual.get("ebitda", {}).get("remaining_budget"),
            },
            {
                "KPI": "Résultat Net",
                "Prévision Annuelle": by_key_annual.get("resultat_net", {}).get("forecast_annual"),
                "Réalisé Cumulé": by_key_annual.get("resultat_net", {}).get("actual_total"),
                "Reste budget": by_key_annual.get("resultat_net", {}).get("remaining_budget"),
            },
        ])

        cycles_df = pd.DataFrame(cycle_status.get("cycles", []))
        annual_alerts_df = pd.DataFrame([
            {
                "Type": "Annuel",
                "Agrégat": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision": r.get("forecast_annual"),
                "Réalisé": r.get("actual_total"),
                "Indice / alerte": r.get("indicator_label") or "—",
                "Niveau": "Défavorable",
            }
            for r in annual_raw_rows if r.get("alert_level") == "negative"
        ])
        monthly_alerts_df = pd.DataFrame([
            {
                "Type": f"Mensuel M{selected_month:02d}",
                "Agrégat": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision": r.get("forecast_value"),
                "Réalisé": r.get("actual_value"),
                "Indice / alerte": "Défavorable",
                "Niveau": "Défavorable",
            }
            for r in monthly if r.get("alert_level") == "negative"
        ])

        annual_detail_df = _build_hierarchical_annual_df(annual_raw_rows, sub_ann_map, only_pnl=False)
        monthly_detail_df = _build_hierarchical_monthly_detail_df(
            target_year=target_year,
            cycle_code=effective_budget_cycle,
            detail_months=detail_months,
            include_subaggregates=include_subaggregates,
        ) if include_budget_forecast and include_monthly_forecast else pd.DataFrame()

        global_state_df = _build_global_state_df(
            target_year=target_year,
            cycle_code=effective_budget_cycle,
            annual_rows=annual_raw_rows,
            sub_ann_map=sub_ann_map,
            realized_months=realized_months,
        ) if include_global_state else pd.DataFrame()

        frames: list[tuple[str, pd.DataFrame]] = []
        if include_executive_summary:
            frames.append(("Executive_Summary", executive_df))
        if include_pnl_formatted:
            has_selected = not pnl_selected_df.empty
            has_global = not pnl_global_df.empty
            if has_selected and has_global:
                frames.append(("PnL_Formate_Selection", pnl_selected_df))
                frames.append(("PnL_Formate_Global", pnl_global_df))
            elif has_selected:
                frames.append(("PnL_Formate", pnl_selected_df))
            elif has_global:
                frames.append(("PnL_Formate", pnl_global_df))
        if include_budget_forecast:
            frames.append(("Forecast_Annuel", annual_df))
            frames.append(("Forecast_Annuel_Detail", annual_detail_df))
            if include_monthly_forecast:
                frames.append(("Forecast_Mensuel_Detail", monthly_detail_df))
        if include_global_state:
            frames.append(("Etat_Globale", global_state_df))
        if include_cycles:
            frames.append(("Cycles", cycles_df))
        if include_alerts:
            alerts_df = pd.concat([annual_alerts_df, monthly_alerts_df], ignore_index=True)
            frames.append(("Alertes", alerts_df))

        title_map = {
            "Executive_Summary": "Reporting Décisionnel — Executive Summary",
            "PnL_Formate": "Reporting Décisionnel — P&L Formaté",
            "PnL_Formate_Selection": "Reporting Décisionnel — P&L Formaté (Mois sélectionnés)",
            "PnL_Formate_Global": "Reporting Décisionnel — P&L Formaté (Global)",
            "Forecast_Annuel": "Reporting Décisionnel — Prévision Budget Annuelle",
            "Forecast_Annuel_Detail": "Reporting Décisionnel — Prévision Budget Annuelle Détaillée",
            "Forecast_Mensuel_Detail": "Reporting Décisionnel — Prévision Budget Mensuelle Détaillée",
            "Etat_Globale": "Reporting Décisionnel — État Globale",
            "Cycles": "Reporting Décisionnel — Statut des Cycles",
            "Alertes": "Reporting Décisionnel — Alertes",
        }

        return HTMLResponse(content=_build_print_html(title_map, frames, target_year, effective_budget_cycle))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur impression reporting: {str(e)}")
