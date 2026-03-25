import io
import json
from datetime import date

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from database import db
from modules.forecast.engine import get_annual_comparison, get_comparison, get_cycle_status, get_subagregats

router = APIRouter(
    prefix="/reporting",
    tags=["Reporting"],
    responses={404: {"description": "Non trouvé"}},
)


PNL_LINE_SPECS = [
    ("CA Brut", "ca_brut", "amount"),
    ("Retrocessions", "retrocessions", "amount"),
    ("CA Net", "ca_net", "amount"),
    ("Autres Produits Exploitation", "autres_produits", "amount"),
    ("Total Produits Exploitation", "total_produits", "amount"),
    ("Frais de Personnel", "frais_personnel", "amount"),
    ("Honoraires & Sous-traitance", "honoraires", "amount"),
    ("Frais Commerciaux", "frais_commerciaux", "amount"),
    ("Impôts et taxes", "impots_taxes", "amount"),
    ("Fonctionnement Courant", "fonctionnement", "amount"),
    ("Autres Charges", "autres_charges", "amount"),
    ("Total Charges Courantes", "total_charges", "amount"),
    ("EBITDA", "ebitda", "amount"),
    ("EBITDA %", "ebitda_pct", "pct"),
    ("Produits Financiers", "produits_financiers", "amount"),
    ("Charges Financières", "charges_financieres", "amount"),
    ("Résultat Financier", "resultat_financier", "amount"),
    ("Dotations Amortissements", "dotations", "amount"),
    ("Produits Exceptionnels", "produits_exceptionnels", "amount"),
    ("Charges Exceptionnelles", "charges_exceptionnelles", "amount"),
    ("Résultat Exceptionnel", "resultat_exceptionnel", "amount"),
    ("Profit avant Impot", "resultat_avant_impot", "amount"),
    ("Impot Societes", "impot_societes", "amount"),
    ("Resultat Net", "resultat_net", "amount"),
    ("Resultat Net %", "resultat_net_pct", "pct"),
]
PNL_KEYS = {k for _, k, _ in PNL_LINE_SPECS}


def _normalize_month_param(target_year: int, month: int | None) -> int:
    if month is not None:
        if month < 1 or month > 12:
            raise ValueError("Mois invalide")
        return month

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT MAX(MONTH(periode)) AS latest_month
            FROM sage_bfc_monthly
            WHERE YEAR(periode) = %s
            """,
            (target_year,),
        )
        row = cursor.fetchone()
    latest = int(row["latest_month"]) if row and row.get("latest_month") is not None else 12
    return latest


def _load_month_resume(target_year: int, month: int) -> dict:
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT resume
            FROM sage_bfc_monthly
            WHERE YEAR(periode) = %s AND MONTH(periode) = %s
            ORDER BY periode DESC
            LIMIT 1
            """,
            (target_year, month),
        )
        row = cursor.fetchone()

    if not row:
        return {}
    resume_raw = row["resume"]
    return resume_raw if isinstance(resume_raw, dict) else json.loads(resume_raw)


def _get_realized_months(target_year: int) -> list[int]:
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT MONTH(periode) AS month_num
            FROM sage_bfc_monthly
            WHERE YEAR(periode) = %s
            ORDER BY month_num
            """,
            (target_year,),
        )
        rows = cursor.fetchall() or []
    return [int(r["month_num"]) for r in rows if r.get("month_num") is not None]


def _load_month_resumes(target_year: int, months: list[int]) -> list[tuple[int, dict]]:
    out = []
    for m in sorted(set(months)):
        out.append((m, _load_month_resume(target_year, m)))
    return out


def _sum_resume_values(resumes: list[dict], key: str) -> float:
    return float(sum(float((r or {}).get(key, 0.0) or 0.0) for r in resumes))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return (numerator / denominator * 100.0) if denominator not in (0, 0.0) else 0.0


def _build_pnl_matrix_df(month_resumes: list[tuple[int, dict]]) -> pd.DataFrame:
    month_cols = [f"M{m:02d}" for m, _ in month_resumes]
    resumes_only = [r for _, r in month_resumes]
    rows = []

    total_ca_net = _sum_resume_values(resumes_only, "ca_net")
    total_ebitda = _sum_resume_values(resumes_only, "ebitda")
    total_resultat_net = _sum_resume_values(resumes_only, "resultat_net")

    for label, key, kind in PNL_LINE_SPECS:
        values = [float((resume or {}).get(key, 0.0) or 0.0) for _, resume in month_resumes]
        row = {"Ligne": label}
        for col_name, value in zip(month_cols, values):
            row[col_name] = value

        if kind == "amount":
            row["Total"] = float(sum(values))
        else:
            if key == "ebitda_pct":
                row["Total"] = _safe_ratio(total_ebitda, total_ca_net)
            elif key == "resultat_net_pct":
                row["Total"] = _safe_ratio(total_resultat_net, total_ca_net)
            else:
                row["Total"] = float(sum(values) / len(values)) if values else 0.0

        rows.append(row)

    return pd.DataFrame(rows)


def _build_pnl_global_df(month_resumes: list[tuple[int, dict]]) -> pd.DataFrame:
    resumes_only = [r for _, r in month_resumes]
    total_ca_net = _sum_resume_values(resumes_only, "ca_net")
    total_ebitda = _sum_resume_values(resumes_only, "ebitda")
    total_resultat_net = _sum_resume_values(resumes_only, "resultat_net")

    rows = []
    for label, key, kind in PNL_LINE_SPECS:
        if kind == "amount":
            value = _sum_resume_values(resumes_only, key)
        else:
            if key == "ebitda_pct":
                value = _safe_ratio(total_ebitda, total_ca_net)
            elif key == "resultat_net_pct":
                value = _safe_ratio(total_resultat_net, total_ca_net)
            else:
                seq = [float((r or {}).get(key, 0.0) or 0.0) for r in resumes_only]
                value = float(sum(seq) / len(seq)) if seq else 0.0

        rows.append({"Ligne": label, "Valeur globale": value})

    return pd.DataFrame(rows)


def _export_label(alert_level: str | None) -> str:
    if alert_level == "negative":
        return "Défavorable"
    if alert_level == "positive":
        return "Favorable"
    return "Neutre"


def _badge_label(alert_level: str | None) -> str:
    if alert_level == "negative":
        return "🔴 Défavorable"
    if alert_level == "positive":
        return "🟢 Favorable"
    return "🟡 Neutre"


def _build_annual_forecast_export_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "Agrégat": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision annuelle": r.get("forecast_annual"),
                "Réalisé cumulé": r.get("actual_total"),
                "Taux réalisation annuel": r.get("taux_realisation_annuel_pct"),
                "Reste budget": r.get("remaining_budget"),
                "Indice / alerte": r.get("indicator_label") or _export_label(r.get("alert_level")),
                "Niveau alerte": _export_label(r.get("alert_level")),
            }
        )
    return out


def _build_monthly_forecast_export_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "Agrégat": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision": r.get("forecast_value"),
                "Réalisé": r.get("actual_value"),
                "Écart": r.get("ecart_value"),
                "Écart %": r.get("ecart_pct"),
                "Indice / alerte": _export_label(r.get("alert_level")),
                "Modèle": r.get("model_name"),
            }
        )
    return out


def _build_hierarchical_annual_df(
    annual_rows: list[dict],
    sub_ann_map: dict[str, list[dict]],
    only_pnl: bool = False,
) -> pd.DataFrame:
    out = []
    for r in annual_rows:
        if only_pnl and r.get("agregat_key") not in PNL_KEYS:
            continue

        key = r.get("agregat_key")
        out.append(
            {
                "Niveau": "Agrégat",
                "Libellé": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision annuelle": r.get("forecast_annual"),
                "Réalisé cumulé": r.get("actual_total"),
                "Taux réalisation annuel": r.get("taux_realisation_annuel_pct"),
                "Reste budget": r.get("remaining_budget"),
                "Indice / alerte": r.get("indicator_label") or _badge_label(r.get("alert_level")),
                "Statut": _badge_label(r.get("alert_level")),
            }
        )

        for item in sub_ann_map.get(key, []):
            out.append(
                {
                    "Niveau": "Sous-agrégat",
                    "Libellé": f"↳ {item.get('subagregat_label')}",
                    "Nature": r.get("nature"),
                    "Prévision annuelle": item.get("forecast_value"),
                    "Réalisé cumulé": item.get("actual_value"),
                    "Taux réalisation annuel": item.get("taux_realisation_annuel_pct"),
                    "Reste budget": item.get("remaining_budget"),
                    "Indice / alerte": item.get("indicator_label") or _badge_label(item.get("alert_level")),
                    "Statut": _badge_label(item.get("alert_level")),
                }
            )

    return pd.DataFrame(out)


def _resolve_pnl_months(
    realized_months: list[int],
    pnl_scope: str,
    selected_month: int,
    pnl_months: list[int] | None,
) -> list[int]:
    realized_set = set(realized_months)
    if pnl_scope not in {"selected", "all", "global"}:
        raise ValueError("pnl_scope invalide. Valeurs: selected, all")

    if pnl_scope in {"all", "global"}:
        months = list(realized_months)
    else:
        chosen = pnl_months or [selected_month]
        months = [m for m in chosen if m in realized_set]

    if not months:
        raise ValueError("Aucun mois réalisé disponible pour le P&L formaté")

    return sorted(set(months))


def _build_pnl_formatted_hierarchical_df(
    target_year: int,
    cycle_code: str,
    annual_rows: list[dict],
    sub_ann_map: dict[str, list[dict]],
    pnl_months: list[int],
    pnl_scope: str,
) -> pd.DataFrame:
    monthly_by_key: dict[tuple[str, int], float] = {}
    for m in pnl_months:
        for row in get_comparison(target_year=target_year, cycle_code=cycle_code, month=m):
            key = row.get("agregat_key")
            if not key or key not in PNL_KEYS:
                continue
            monthly_by_key[(key, m)] = float(row.get("actual_value") or 0.0)

    sub_actuals: dict[tuple[str, str, int], float] = {}
    for agg_key in [r.get("agregat_key") for r in annual_rows if r.get("agregat_key") in PNL_KEYS]:
        if not agg_key:
            continue
        for m in pnl_months:
            sub_data = get_subagregats(target_year=target_year, cycle_code=cycle_code, agregat_key=agg_key, month=m)
            for item in sub_data.get("items", []):
                skey = item.get("subagregat_key")
                if not skey:
                    continue
                tk = (agg_key, skey, m)
                sub_actuals[tk] = float(item.get("actual_value") or 0.0)

    out: list[dict] = []
    is_global = pnl_scope in {"all", "global"}
    month_labels = [f"M{m:02d}" for m in pnl_months]

    for r in annual_rows:
        key = r.get("agregat_key")
        if key not in PNL_KEYS:
            continue
        base_row = {
            "Niveau": "Agrégat",
            "Libellé": r.get("agregat_label"),
            "Nature": r.get("nature"),
        }
        if is_global:
            base_row["Réalisé global"] = float(sum(monthly_by_key.get((key, m), 0.0) for m in pnl_months))
        else:
            for m, col in zip(pnl_months, month_labels):
                base_row[col] = float(monthly_by_key.get((key, m), 0.0))
        out.append(base_row)

        for item in sub_ann_map.get(key, []):
            sub_row = {
                "Niveau": "Sous-agrégat",
                "Libellé": f"↳ {item.get('subagregat_label')}",
                "Nature": r.get("nature"),
            }
            skey = item.get("subagregat_key")
            if is_global:
                sub_row["Réalisé global"] = float(sum(sub_actuals.get((key, skey, m), 0.0) for m in pnl_months))
            else:
                for m, col in zip(pnl_months, month_labels):
                    sub_row[col] = float(sub_actuals.get((key, skey, m), 0.0))
            out.append(sub_row)

    return pd.DataFrame(out)


def _resolve_detail_months(
    realized_months: list[int],
    selected_month: int,
    detail_months: list[int] | None,
) -> list[int]:
    realized_set = set(realized_months)
    chosen = detail_months or [selected_month]
    months = [m for m in chosen if m in realized_set]
    if not months:
        raise ValueError("Aucun mois réalisé disponible pour Forecast_Mensuel_Detail")
    return sorted(set(months))


def _build_hierarchical_monthly_detail_df(
    target_year: int,
    cycle_code: str,
    detail_months: list[int],
    include_subaggregates: bool,
) -> pd.DataFrame:
    out: list[dict] = []
    for idx_month, m in enumerate(detail_months):
        monthly_rows = get_comparison(target_year=target_year, cycle_code=cycle_code, month=m)
        for row in monthly_rows:
            key = row.get("agregat_key")
            out.append(
                {
                    "Mois": f"M{m:02d}",
                    "Niveau": "Agrégat",
                    "Libellé": row.get("agregat_label"),
                    "Nature": row.get("nature"),
                    "Prévision": row.get("forecast_value"),
                    "Réalisé": row.get("actual_value"),
                    "Écart": row.get("ecart_value"),
                    "Écart %": row.get("ecart_pct"),
                    "Indice / alerte": _badge_label(row.get("alert_level")),
                    "Statut": _badge_label(row.get("alert_level")),
                }
            )

            if not include_subaggregates or not key:
                continue

            sub = get_subagregats(target_year, cycle_code, key, m)
            for item in sub.get("items", []):
                f_val = float(item.get("forecast_value") or 0.0)
                a_val = float(item.get("actual_value") or 0.0)
                ecart = a_val - f_val
                ecart_pct = (ecart / abs(f_val) * 100.0) if f_val != 0 else 0.0
                out.append(
                    {
                        "Mois": f"M{m:02d}",
                        "Niveau": "Sous-agrégat",
                        "Libellé": f"↳ {item.get('subagregat_label')}",
                        "Nature": row.get("nature"),
                        "Prévision": f_val,
                        "Réalisé": a_val,
                        "Écart": ecart,
                        "Écart %": ecart_pct,
                        "Indice / alerte": item.get("indicator_label") or _badge_label(item.get("alert_level")),
                        "Statut": _badge_label(item.get("alert_level")),
                    }
                )

        if idx_month < len(detail_months) - 1:
            out.append(
                {
                    "Mois": "",
                    "Niveau": "",
                    "Libellé": "",
                    "Nature": "",
                    "Prévision": "",
                    "Réalisé": "",
                    "Écart": "",
                    "Écart %": "",
                    "Indice / alerte": "",
                    "Statut": "",
                }
            )

    return pd.DataFrame(out)


@router.get("/preview")
def get_reporting_preview(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
    month: int | None = Query(None, ge=1, le=12),
):
    try:
        selected_month = _normalize_month_param(target_year, month)
        realized_months = _get_realized_months(target_year)
        annual = get_annual_comparison(target_year=target_year, cycle_code=cycle_code)
        monthly = get_comparison(target_year=target_year, cycle_code=cycle_code, month=selected_month)
        cycle_status = get_cycle_status(target_year=target_year)

        by_key_annual = {r["agregat_key"]: r for r in annual.get("rows", [])}
        kpis = {
            "ca_net": by_key_annual.get("ca_net", {}),
            "ebitda": by_key_annual.get("ebitda", {}),
            "resultat_net": by_key_annual.get("resultat_net", {}),
        }

        annual_alerts = [r for r in annual.get("rows", []) if r.get("alert_level") == "negative"]
        monthly_alerts = [r for r in monthly if r.get("alert_level") == "negative"]
        annual_rows = annual.get("rows", [])

        return {
            "target_year": target_year,
            "cycle_code": cycle_code,
            "month": selected_month,
            "kpis": kpis,
            "annual_alerts_count": len(annual_alerts),
            "monthly_alerts_count": len(monthly_alerts),
            "annual_rows": annual_rows,
            "available_months": realized_months,
            "cycles": cycle_status.get("cycles", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur preview reporting: {str(e)}")


@router.get("/export/excel")
def export_reporting_excel(
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
):
    try:
        if not any([
            include_executive_summary,
            include_pnl_formatted,
            include_budget_forecast,
            include_cycles,
            include_alerts,
        ]):
            raise ValueError("Aucun contenu sélectionné pour l'export")

        selected_month = _normalize_month_param(target_year, month)
        effective_budget_cycle = budget_cycle_code or cycle_code
        realized_months = _get_realized_months(target_year)

        detail_months = []
        if include_budget_forecast and include_monthly_forecast:
            detail_months = _resolve_detail_months(
                realized_months=realized_months,
                selected_month=selected_month,
                detail_months=monthly_detail_months,
            )

        effective_pnl_months = []
        if include_pnl_formatted:
            effective_pnl_months = _resolve_pnl_months(
                realized_months=realized_months,
                pnl_scope=pnl_scope,
                selected_month=selected_month,
                pnl_months=pnl_months,
            )

        annual = get_annual_comparison(target_year=target_year, cycle_code=effective_budget_cycle)
        monthly = get_comparison(target_year=target_year, cycle_code=effective_budget_cycle, month=selected_month)
        cycle_status = get_cycle_status(target_year=target_year)

        annual_raw_rows = annual.get("rows", [])
        annual_df = pd.DataFrame(_build_annual_forecast_export_rows(annual_raw_rows))

        sub_ann_map: dict[str, list[dict]] = {}
        need_annual_sub = include_subaggregates or include_pnl_formatted
        if need_annual_sub:
            for row in annual_raw_rows:
                key = row.get("agregat_key")
                if not key:
                    continue
                sub_ann_map[key] = list(get_subagregats(target_year, effective_budget_cycle, key, None).get("items", []))

        pnl_df = pd.DataFrame()

        if include_pnl_formatted:
            annual_base = get_annual_comparison(target_year=target_year, cycle_code=cycle_code)
            annual_pnl_rows = annual_base.get("rows", [])
            pnl_sub_map: dict[str, list[dict]] = {}
            for row in annual_pnl_rows:
                key = row.get("agregat_key")
                if not key or key not in PNL_KEYS:
                    continue
                pnl_sub_map[key] = list(get_subagregats(target_year, cycle_code, key, None).get("items", []))

            pnl_df = _build_pnl_formatted_hierarchical_df(
                target_year=target_year,
                cycle_code=cycle_code,
                annual_rows=annual_pnl_rows,
                sub_ann_map=pnl_sub_map,
                pnl_months=effective_pnl_months,
                pnl_scope=pnl_scope,
            )

        by_key_annual = {r["agregat_key"]: r for r in annual_raw_rows}
        executive_rows = [
            {
                "KPI": "CA Net",
                "Prévision Annuelle": by_key_annual.get("ca_net", {}).get("forecast_annual"),
                "Réalisé Cumulé": by_key_annual.get("ca_net", {}).get("actual_total"),
                "Taux Réalisation %": by_key_annual.get("ca_net", {}).get("taux_realisation_annuel_pct"),
                "Indice": by_key_annual.get("ca_net", {}).get("indicator_label"),
                "Alerte": by_key_annual.get("ca_net", {}).get("alert_level"),
            },
            {
                "KPI": "EBITDA",
                "Prévision Annuelle": by_key_annual.get("ebitda", {}).get("forecast_annual"),
                "Réalisé Cumulé": by_key_annual.get("ebitda", {}).get("actual_total"),
                "Taux Réalisation %": by_key_annual.get("ebitda", {}).get("taux_realisation_annuel_pct"),
                "Indice": by_key_annual.get("ebitda", {}).get("indicator_label"),
                "Alerte": by_key_annual.get("ebitda", {}).get("alert_level"),
            },
            {
                "KPI": "Résultat Net",
                "Prévision Annuelle": by_key_annual.get("resultat_net", {}).get("forecast_annual"),
                "Réalisé Cumulé": by_key_annual.get("resultat_net", {}).get("actual_total"),
                "Taux Réalisation %": by_key_annual.get("resultat_net", {}).get("taux_realisation_annuel_pct"),
                "Indice": by_key_annual.get("resultat_net", {}).get("indicator_label"),
                "Alerte": by_key_annual.get("resultat_net", {}).get("alert_level"),
            },
        ]
        executive_df = pd.DataFrame(executive_rows)

        cycles_df = pd.DataFrame(cycle_status.get("cycles", []))

        annual_alerts_df = pd.DataFrame([
            {
                "Type": "Annuel",
                "Agrégat": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision": r.get("forecast_annual"),
                "Réalisé": r.get("actual_total"),
                "Indice / alerte": r.get("indicator_label") or "—",
                "Niveau": _export_label(r.get("alert_level")),
            }
            for r in annual_raw_rows
            if r.get("alert_level") == "negative"
        ])
        monthly_alerts_df = pd.DataFrame([
            {
                "Type": f"Mensuel M{selected_month:02d}",
                "Agrégat": r.get("agregat_label"),
                "Nature": r.get("nature"),
                "Prévision": r.get("forecast_value"),
                "Réalisé": r.get("actual_value"),
                "Indice / alerte": _export_label(r.get("alert_level")),
                "Niveau": _export_label(r.get("alert_level")),
            }
            for r in monthly
            if r.get("alert_level") == "negative"
        ])

        annual_detail_df = _build_hierarchical_annual_df(annual_raw_rows, sub_ann_map, only_pnl=False)
        monthly_detail_df = _build_hierarchical_monthly_detail_df(
            target_year=target_year,
            cycle_code=effective_budget_cycle,
            detail_months=detail_months,
            include_subaggregates=include_subaggregates,
        ) if include_budget_forecast and include_monthly_forecast else pd.DataFrame()

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            if include_executive_summary:
                executive_df.to_excel(writer, sheet_name="Executive_Summary", index=False)
            if include_pnl_formatted:
                pnl_df.to_excel(writer, sheet_name="PnL_Formate", index=False)
            if include_budget_forecast:
                annual_df.to_excel(writer, sheet_name="Forecast_Annuel", index=False)
                annual_detail_df.to_excel(writer, sheet_name="Forecast_Annuel_Detail", index=False)
                if include_monthly_forecast:
                    monthly_detail_df.to_excel(writer, sheet_name="Forecast_Mensuel_Detail", index=False)
            if include_cycles:
                cycles_df.to_excel(writer, sheet_name="Cycles", index=False)
            if include_alerts:
                alerts_start_row = 0
                if not annual_alerts_df.empty:
                    annual_alerts_df.to_excel(writer, sheet_name="Alertes", index=False, startrow=alerts_start_row)
                    alerts_start_row += len(annual_alerts_df) + 3
                if not monthly_alerts_df.empty:
                    monthly_alerts_df.to_excel(writer, sheet_name="Alertes", index=False, startrow=alerts_start_row)

            workbook = writer.book
            money_fmt = workbook.add_format({"num_format": "#,##0.000"})
            pct_fmt = workbook.add_format({"num_format": "0.000"})
            header_fmt = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1E3A8A", "border": 1, "align": "center"})
            kpi_row_fmt = workbook.add_format({"bg_color": "#EEF2FF", "bold": True})
            aggregate_row_fmt = workbook.add_format({"bg_color": "#E0F2FE", "bold": True})
            subaggregate_row_fmt = workbook.add_format({"bg_color": "#F8FAFC"})
            pnl_products_fmt = workbook.add_format({"bg_color": "#ECFDF5"})
            pnl_charges_fmt = workbook.add_format({"bg_color": "#FEF2F2"})
            pnl_result_fmt = workbook.add_format({"bg_color": "#EFF6FF", "bold": True})
            pnl_products_agg_fmt = workbook.add_format({"bg_color": "#ECFDF5", "bold": True})
            pnl_charges_agg_fmt = workbook.add_format({"bg_color": "#FEF2F2", "bold": True})
            pnl_result_agg_fmt = workbook.add_format({"bg_color": "#EFF6FF", "bold": True})

            for sheet_name in writer.sheets.keys():
                ws = writer.sheets[sheet_name]
                df_source = None
                if sheet_name == "Executive_Summary":
                    df_source = executive_df
                elif sheet_name == "PnL_Formate":
                    df_source = pnl_df
                elif sheet_name == "Forecast_Annuel":
                    df_source = annual_df
                elif sheet_name == "Forecast_Annuel_Detail":
                    df_source = annual_detail_df
                elif sheet_name == "Forecast_Mensuel_Detail":
                    df_source = monthly_detail_df
                elif sheet_name == "Cycles":
                    df_source = cycles_df
                elif sheet_name == "Alertes":
                    df_source = pd.concat([annual_alerts_df, monthly_alerts_df], ignore_index=True)

                if df_source is not None and not df_source.empty:
                    ws.autofilter(0, 0, len(df_source), max(len(df_source.columns) - 1, 0))

                ws.freeze_panes(1, 0)
                ws.set_row(0, 22, header_fmt)
                ws.set_column(0, 0, 34)
                ws.set_column(1, 30, 18, money_fmt)

                if df_source is not None and not df_source.empty:
                    for idx, col in enumerate(df_source.columns):
                        name = str(col).lower()
                        if "taux" in name or "%" in name:
                            ws.set_column(idx, idx, 16, pct_fmt)
                        elif any(token in name for token in ["nature", "indice", "alerte", "modèle", "agrégat", "sous-agrégat", "mois"]):
                            ws.set_column(idx, idx, 28)

                    if "statut" in [str(c).lower() for c in df_source.columns]:
                        stat_idx = [str(c).lower() for c in df_source.columns].index("statut")
                        ws.conditional_format(1, stat_idx, len(df_source), stat_idx, {
                            "type": "text",
                            "criteria": "containing",
                            "value": "Défavorable",
                            "format": workbook.add_format({"font_color": "#991B1B", "bg_color": "#FEE2E2", "bold": True}),
                        })
                        ws.conditional_format(1, stat_idx, len(df_source), stat_idx, {
                            "type": "text",
                            "criteria": "containing",
                            "value": "Favorable",
                            "format": workbook.add_format({"font_color": "#14532D", "bg_color": "#DCFCE7", "bold": True}),
                        })
                        ws.conditional_format(1, stat_idx, len(df_source), stat_idx, {
                            "type": "text",
                            "criteria": "containing",
                            "value": "Neutre",
                            "format": workbook.add_format({"font_color": "#854D0E", "bg_color": "#FEF9C3", "bold": True}),
                        })

                    if sheet_name == "Executive_Summary":
                        for ridx in range(1, len(df_source) + 1):
                            ws.set_row(ridx, 20, kpi_row_fmt)

                    if sheet_name in {"Forecast_Annuel_Detail", "Forecast_Mensuel_Detail", "PnL_Formate"}:
                        lvl_idx = [str(c).lower() for c in df_source.columns].index("niveau") if "Niveau" in df_source.columns else -1
                        lib_idx = [str(c).lower() for c in df_source.columns].index("libellé") if "Libellé" in df_source.columns else -1
                        for ridx, row in enumerate(df_source.to_dict(orient="records"), start=1):
                            level = row.get("Niveau")
                            if level == "Agrégat":
                                ws.set_row(ridx, 20, aggregate_row_fmt)
                            elif level == "Sous-agrégat":
                                ws.set_row(ridx, 20, subaggregate_row_fmt)

                            if sheet_name == "PnL_Formate":
                                label = str(row.get("Libellé") or "").lower()
                                is_agg = row.get("Niveau") == "Agrégat"
                                if any(x in label for x in ["charges", "frais", "impot", "dotations"]):
                                    ws.set_row(ridx, 20, pnl_charges_agg_fmt if is_agg else pnl_charges_fmt)
                                elif any(x in label for x in ["résultat", "resultat", "ebitda", "profit"]):
                                    ws.set_row(ridx, 20, pnl_result_agg_fmt if is_agg else pnl_result_fmt)
                                else:
                                    ws.set_row(ridx, 20, pnl_products_agg_fmt if is_agg else pnl_products_fmt)

                            if lvl_idx >= 0 and lib_idx >= 0 and row.get("Niveau") == "Sous-agrégat":
                                ws.write(ridx, lib_idx, row.get("Libellé"), workbook.add_format({"italic": True, "font_color": "#334155"}))

                if sheet_name == "PnL_Formate" and df_source is not None and not df_source.empty:
                    cols = list(df_source.columns)
                    if "Libellé" in cols:
                        lib_idx = cols.index("Libellé")
                        max_len = max([len(str(v or "")) for v in df_source["Libellé"].tolist()] + [len("Libellé")])
                        ws.set_column(lib_idx, lib_idx, min(max(max_len + 2, 28), 48))

                    month_indices = [i for i, c in enumerate(cols) if str(c).startswith("M")]
                    if month_indices:
                        month_w = 13 if len(month_indices) <= 6 else 11
                        for i in month_indices:
                            ws.set_column(i, i, month_w, money_fmt)

                    if "Nature" in cols:
                        n_idx = cols.index("Nature")
                        ws.set_column(n_idx, n_idx, 16)

                    if "Niveau" in cols:
                        lv_idx = cols.index("Niveau")
                        ws.set_column(lv_idx, lv_idx, 14)

                    ws.freeze_panes(1, 3)

        output.seek(0)
        filename = f"Reporting_OLEA_{target_year}_{cycle_code}_M{selected_month:02d}.xlsx"

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur export reporting Excel: {str(e)}")
