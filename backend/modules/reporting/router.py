import io
import json
import unicodedata
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from xlsxwriter.utility import xl_col_to_name

from database import db
from modules.auth.dependencies import get_current_user, require_permission, restrict_superadmin
from modules.forecast.engine import get_annual_comparison, get_comparison, get_cycle_status, get_subagregats

router = APIRouter(
    prefix="/reporting",
    tags=["Reporting"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("reporting"))],
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


def _export_label_key(value) -> str:
    """Normalise les libellés utilisés pour relier les feuilles Excel."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(normalized.encode("ascii", "ignore").decode("ascii").casefold().split())


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
                "Reste budget": r.get("remaining_budget"),
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
                "Prévision annuelle": r.get("forecast_annual") if r.get("forecast_annual") is not None else 0.0,
                "Réalisé cumulé": r.get("actual_total") if r.get("actual_total") is not None else 0.0,
                "Reste budget": r.get("remaining_budget") if r.get("remaining_budget") is not None else 0.0,
            }
        )

        for item in sub_ann_map.get(key, []):
            out.append(
                {
                    "Niveau": "Sous-agrégat",
                    "Libellé": f"↳ {item.get('subagregat_label')}",
                    "Nature": r.get("nature"),
                    "Prévision annuelle": item.get("forecast_value") if item.get("forecast_value") is not None else 0.0,
                    "Réalisé cumulé": item.get("actual_value") if item.get("actual_value") is not None else 0.0,
                    "Reste budget": item.get("remaining_budget") if item.get("remaining_budget") is not None else 0.0,
                }
            )

    return pd.DataFrame(out)


def _remaining_budget_semantic(forecast_value: float, actual_value: float, nature: str = "charge") -> float:
    if nature == "produit":
        if float(forecast_value) >= 0:
            if float(actual_value) > float(forecast_value):
                # Dépassement de budget pour un produit (positif)
                return float(actual_value) - float(forecast_value)
        else:
            if float(actual_value) < float(forecast_value):
                # Dépassement de budget pour un produit (négatif)
                return float(forecast_value) - float(actual_value)

    base = float(forecast_value) - float(actual_value)
    return base if float(forecast_value) >= 0 else -base


def _format_df_reste_budget(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    
    reste_col = None
    for c in df.columns:
        if str(c).lower().strip() == "reste budget":
            reste_col = c
            break
            
    if not reste_col:
        return df
        
    forecast_col = None
    for c in df.columns:
        if str(c).lower().strip() in {"prévision annuelle", "prévision"}:
            forecast_col = c
            break
            
    actual_col = None
    for c in df.columns:
        if str(c).lower().strip() in {"réalisé cumulé", "réalisé"}:
            actual_col = c
            break
            
    if not forecast_col:
        for c in df.columns:
            if str(c).lower().strip() == "prévision annuelle":
                forecast_col = c
                break
    if not actual_col:
        for c in df.columns:
            if str(c).lower().strip() == "réalisé cumulé":
                actual_col = c
                break

    def _row_is_product(row: dict) -> bool:
        nature = str(row.get("Nature") or "").lower().strip()
        if nature == "produit":
            return True
        if nature == "charge":
            return False
        
        lib = str(row.get("Libellé") or row.get("KPI") or row.get("Agrégat") or "").lower().strip()
        lib = lib.replace("↳", "").strip()
        
        product_indicators = [
            "ca net", "ebitda", "resultat net", "résultat net", "ca brut", 
            "autres produits", "produits financiers", "produits exceptionnels",
            "profit avant impot", "profit avant impôt"
        ]
        return any(ind in lib for ind in product_indicators)

    new_rows = []
    for row in df.to_dict(orient="records"):
        val = row.get(reste_col)
        if val is not None and _row_is_product(row):
            try:
                val_float = float(val)
                f_val = row.get(forecast_col)
                a_val = row.get(actual_col)
                if f_val is not None and a_val is not None:
                    f_float = float(f_val)
                    a_float = float(a_val)
                    is_exceeded = (
                        a_float > f_float if f_float >= 0 else a_float < f_float
                    )
                    if is_exceeded and val_float > 0:
                        formatted = f"{val_float:,.3f}".replace(",", " ").replace(".", ",")
                        row[reste_col] = f"+{formatted}"
            except (ValueError, TypeError):
                pass
        new_rows.append(row)
        
    return pd.DataFrame(new_rows)


DERIVED_BUDGET_DEPENDENCIES = {
    "ca_net": ("ca_brut", "retrocessions"),
    "total_produits": ("ca_net", "autres_produits"),
    "total_charges": (
        "frais_personnel",
        "honoraires",
        "frais_commerciaux",
        "impots_taxes",
        "fonctionnement",
        "autres_charges",
    ),
    "ebitda": ("total_produits", "total_charges"),
    "ebitda_pct": ("ebitda", "ca_net"),
    "resultat_financier": ("produits_financiers", "charges_financieres"),
    "resultat_exceptionnel": ("produits_exceptionnels", "charges_exceptionnelles"),
    "resultat_avant_impot": ("ebitda", "resultat_financier", "dotations", "resultat_exceptionnel"),
    "resultat_net": ("resultat_avant_impot", "impot_societes"),
    "resultat_net_pct": ("resultat_net", "ca_net"),
}


def _formula_number(value) -> float:
    try:
        return float(
            str(value)
            .replace("\u202f", "")
            .replace(" ", "")
            .replace(",", ".")
        )
    except (TypeError, ValueError):
        return 0.0


def _derived_budget_formula(agregat_key: str, row_refs: dict[str, int], value_col_idx: int) -> str | None:
    dependencies = DERIVED_BUDGET_DEPENDENCIES.get(agregat_key)
    if not dependencies or any(key not in row_refs for key in dependencies):
        return None

    col = xl_col_to_name(value_col_idx)
    ref = lambda key: f"{col}{row_refs[key]}"

    if agregat_key == "ca_net":
        return f"={ref('ca_brut')}-{ref('retrocessions')}"
    if agregat_key == "total_produits":
        return f"={ref('ca_net')}+{ref('autres_produits')}"
    if agregat_key == "total_charges":
        return "=" + "+".join(ref(key) for key in dependencies)
    if agregat_key == "ebitda":
        return f"={ref('total_produits')}-{ref('total_charges')}"
    if agregat_key == "ebitda_pct":
        return f"=IFERROR({ref('ebitda')}/{ref('ca_net')}*100,0)"
    if agregat_key == "resultat_financier":
        return f"={ref('produits_financiers')}-{ref('charges_financieres')}"
    if agregat_key == "resultat_exceptionnel":
        return f"={ref('produits_exceptionnels')}-{ref('charges_exceptionnelles')}"
    if agregat_key == "resultat_avant_impot":
        return f"={ref('ebitda')}+{ref('resultat_financier')}-{ref('dotations')}+{ref('resultat_exceptionnel')}"
    if agregat_key == "resultat_net":
        return f"={ref('resultat_avant_impot')}-{ref('impot_societes')}"
    if agregat_key == "resultat_net_pct":
        return f"=IFERROR({ref('resultat_net')}/{ref('ca_net')}*100,0)"
    return None


def _hierarchical_formula_context(
    dataframe: pd.DataFrame,
    data_start_row: int,
    aggregate_key_by_label: dict[str, str],
) -> list[tuple[dict[str, int], dict[int, list[int]]]]:
    """Construit les groupes de lignes et les plages de sous-agrégats par période."""
    rows = dataframe.to_dict(orient="records")
    has_month = "Mois" in dataframe.columns
    groups: dict[str, list[int]] = {}
    for offset, row in enumerate(rows):
        if str(row.get("Niveau") or "") not in {"Agrégat", "Sous-agrégat"}:
            continue
        group_key = str(row.get("Mois") or "ANNUEL") if has_month else "ANNUEL"
        groups.setdefault(group_key, []).append(offset)

    contexts = []
    for offsets in groups.values():
        row_refs: dict[str, int] = {}
        children_by_parent: dict[int, list[int]] = {}
        current_parent = None

        for offset in offsets:
            row = rows[offset]
            level = str(row.get("Niveau") or "")
            excel_row = data_start_row + offset + 1
            if level == "Agrégat":
                current_parent = offset
                label = str(row.get("Libellé") or "")
                agregat_key = aggregate_key_by_label.get(label)
                if agregat_key:
                    row_refs[agregat_key] = excel_row
                children_by_parent.setdefault(offset, [])
            elif level == "Sous-agrégat" and current_parent is not None:
                children_by_parent.setdefault(current_parent, []).append(offset)

        contexts.append((row_refs, children_by_parent))
    return contexts


def _write_budget_formulas(
    worksheet,
    dataframe: pd.DataFrame,
    data_start_row: int,
    money_format,
    positive_money_format,
    percent_format,
    aggregate_formula_format,
    aggregate_percent_format,
    linked_formula_format,
    linked_percent_format,
    sheet_name: str,
    aggregate_key_by_label: dict[str, str],
    annual_dataframe: pd.DataFrame | None = None,
    annual_detail_dataframe: pd.DataFrame | None = None,
) -> None:
    """Écrit toute la chaîne de calcul budget dans le classeur Excel."""
    if dataframe is None or dataframe.empty:
        return

    rows = dataframe.to_dict(orient="records")
    columns = list(dataframe.columns)
    column_indexes = {str(name).lower().strip(): idx for idx, name in enumerate(columns)}
    forecast_idx = column_indexes.get("prévision annuelle", column_indexes.get("prévision"))
    actual_idx = column_indexes.get("réalisé cumulé", column_indexes.get("réalisé"))
    nature_idx = column_indexes.get("nature")
    remaining_idx = column_indexes.get("reste budget")
    difference_idx = column_indexes.get("écart")
    difference_pct_idx = column_indexes.get("écart %")

    value_column_indexes = [idx for idx in (forecast_idx, actual_idx) if idx is not None]

    if sheet_name in {"Forecast_Annuel_Detail", "Forecast_Mensuel_Detail"}:
        contexts = _hierarchical_formula_context(dataframe, data_start_row, aggregate_key_by_label)
        for row_refs, children_by_parent in contexts:
            for parent_offset, child_offsets in children_by_parent.items():
                parent_row = rows[parent_offset]
                label = str(parent_row.get("Libellé") or "")
                agregat_key = aggregate_key_by_label.get(label)
                if not agregat_key:
                    continue

                for value_col_idx in value_column_indexes:
                    formula = _derived_budget_formula(agregat_key, row_refs, value_col_idx)
                    if formula is None and child_offsets:
                        col = xl_col_to_name(value_col_idx)
                        first_child_row = data_start_row + child_offsets[0] + 1
                        last_child_row = data_start_row + child_offsets[-1] + 1
                        formula = f"=SUM({col}{first_child_row}:{col}{last_child_row})"
                    if formula is None:
                        continue

                    cached_value = _formula_number(parent_row.get(columns[value_col_idx]))
                    formula_format = (
                        aggregate_percent_format
                        if agregat_key in {"ebitda_pct", "resultat_net_pct"}
                        else aggregate_formula_format
                    )
                    worksheet.write_formula(
                        data_start_row + parent_offset,
                        value_col_idx,
                        formula,
                        formula_format,
                        cached_value,
                    )

    if sheet_name == "Forecast_Annuel" and annual_detail_dataframe is not None and not annual_detail_dataframe.empty:
        detail_columns = list(annual_detail_dataframe.columns)
        detail_indexes = {str(name).lower().strip(): idx for idx, name in enumerate(detail_columns)}
        detail_rows_by_label = {
            str(row.get("Libellé") or ""): data_start_row + offset + 1
            for offset, row in enumerate(annual_detail_dataframe.to_dict(orient="records"))
            if str(row.get("Niveau") or "") == "Agrégat"
        }
        for offset, row in enumerate(rows):
            label = str(row.get("Agrégat") or "")
            detail_excel_row = detail_rows_by_label.get(label)
            agregat_key = aggregate_key_by_label.get(label)
            if detail_excel_row is None or not agregat_key:
                continue
            for local_idx, detail_name in (
                (forecast_idx, "prévision annuelle"),
                (actual_idx, "réalisé cumulé"),
            ):
                detail_idx = detail_indexes.get(detail_name)
                if local_idx is None or detail_idx is None:
                    continue
                detail_ref = f"{xl_col_to_name(detail_idx)}{detail_excel_row}"
                cached_value = _formula_number(row.get(columns[local_idx]))
                formula_format = (
                    linked_percent_format
                    if agregat_key in {"ebitda_pct", "resultat_net_pct"}
                    else linked_formula_format
                )
                worksheet.write_formula(
                    data_start_row + offset,
                    local_idx,
                    f"='Forecast_Annuel_Detail'!{detail_ref}",
                    formula_format,
                    cached_value,
                )

    if sheet_name == "Executive_Summary" and annual_dataframe is not None and not annual_dataframe.empty:
        annual_columns = list(annual_dataframe.columns)
        annual_indexes = {str(name).lower().strip(): idx for idx, name in enumerate(annual_columns)}
        annual_rows_by_label = {
            _export_label_key(row.get("Agrégat")): data_start_row + offset + 1
            for offset, row in enumerate(annual_dataframe.to_dict(orient="records"))
            if row.get("Agrégat")
        }
        executive_links = (
            ("prévision annuelle", "prévision annuelle"),
            ("réalisé cumulé", "réalisé cumulé"),
            ("reste budget", "reste budget"),
        )
        for offset, row in enumerate(rows):
            label = _export_label_key(row.get("KPI"))
            annual_excel_row = annual_rows_by_label.get(label)
            if annual_excel_row is None:
                continue
            for local_name, annual_name in executive_links:
                local_idx = column_indexes.get(local_name)
                annual_idx = annual_indexes.get(annual_name)
                if local_idx is None or annual_idx is None:
                    continue
                annual_ref = f"{xl_col_to_name(annual_idx)}{annual_excel_row}"
                worksheet.write_formula(
                    data_start_row + offset,
                    local_idx,
                    f"='Forecast_Annuel'!{annual_ref}",
                    linked_formula_format,
                    _formula_number(row.get(columns[local_idx])),
                )

    for offset, row in enumerate(rows):
        worksheet_row = data_start_row + offset
        excel_row = worksheet_row + 1

        if all(value in (None, "") for value in row.values()):
            continue

        if forecast_idx is not None and actual_idx is not None:
            forecast_ref = f"{xl_col_to_name(forecast_idx)}{excel_row}"
            actual_ref = f"{xl_col_to_name(actual_idx)}{excel_row}"

            if remaining_idx is not None and nature_idx is not None:
                nature_ref = f"{xl_col_to_name(nature_idx)}{excel_row}"
                formula = (
                    f'=IF({nature_ref}="produit",'
                    f"IF({forecast_ref}>=0,IF({actual_ref}>{forecast_ref},{actual_ref}-{forecast_ref},{forecast_ref}-{actual_ref}),"
                    f"IF({actual_ref}<{forecast_ref},{forecast_ref}-{actual_ref},{actual_ref}-{forecast_ref})),"
                    f"IF({forecast_ref}>=0,{forecast_ref}-{actual_ref},{actual_ref}-{forecast_ref}))"
                )
                cached_value = row.get(columns[remaining_idx])
                formula_format = positive_money_format if str(cached_value).strip().startswith("+") else money_format
                worksheet.write_formula(
                    worksheet_row,
                    remaining_idx,
                    formula,
                    formula_format,
                    _formula_number(cached_value),
                )

            if difference_idx is not None:
                difference_ref = f"{xl_col_to_name(difference_idx)}{excel_row}"
                worksheet.write_formula(
                    worksheet_row,
                    difference_idx,
                    f"={actual_ref}-{forecast_ref}",
                    money_format,
                    _formula_number(row.get(columns[difference_idx])),
                )

                if difference_pct_idx is not None:
                    worksheet.write_formula(
                        worksheet_row,
                        difference_pct_idx,
                        f"=IFERROR({difference_ref}/ABS({forecast_ref})*100,0)",
                        percent_format,
                        _formula_number(row.get(columns[difference_pct_idx])),
                    )


def _build_global_state_df(
    target_year: int,
    cycle_code: str,
    annual_rows: list[dict],
    sub_ann_map: dict[str, list[dict]],
    realized_months: list[int],
) -> pd.DataFrame:
    month_labels = [f"M{m:02d}" for m in realized_months]

    agg_actual_monthly: dict[tuple[str, int], float] = {}
    for m in realized_months:
        monthly_rows = get_comparison(target_year=target_year, cycle_code=cycle_code, month=m)
        for row in monthly_rows:
            key = row.get("agregat_key")
            if not key:
                continue
            agg_actual_monthly[(key, m)] = float(row.get("actual_value") or 0.0)

    sub_actual_monthly: dict[tuple[str, str, int], float] = {}
    for row in annual_rows:
        agg_key = row.get("agregat_key")
        if not agg_key:
            continue
        for m in realized_months:
            sub_data = get_subagregats(target_year=target_year, cycle_code=cycle_code, agregat_key=agg_key, month=m)
            for item in sub_data.get("items", []):
                skey = item.get("subagregat_key")
                if not skey:
                    continue
                sub_actual_monthly[(agg_key, skey, m)] = float(item.get("actual_value") or 0.0)

    out: list[dict] = []
    for row in annual_rows:
        key = row.get("agregat_key")
        if not key:
            continue

        line = {
            "Niveau": "Agrégat",
            "Libellé": row.get("agregat_label"),
            "Nature": row.get("nature"),
            "Prévision annuelle": float(row.get("forecast_annual") or 0.0),
        }
        for m, col in zip(realized_months, month_labels):
            line[col] = float(agg_actual_monthly.get((key, m), 0.0))

        line["Réalisé cumulé"] = float(row.get("actual_total") or 0.0)
        line["Reste budget"] = float(row.get("remaining_budget") or 0.0)
        out.append(line)

        for sub in sub_ann_map.get(key, []):
            skey = sub.get("subagregat_key")
            f_val = float(sub.get("forecast_value") or 0.0)
            a_cum = float(sum(sub_actual_monthly.get((key, skey, m), 0.0) for m in realized_months))

            sub_line = {
                "Niveau": "Sous-agrégat",
                "Libellé": f"↳ {sub.get('subagregat_label')}",
                "Nature": row.get("nature"),
                "Prévision annuelle": f_val,
            }
            for m, col in zip(realized_months, month_labels):
                sub_line[col] = float(sub_actual_monthly.get((key, skey, m), 0.0))

            sub_line["Réalisé cumulé"] = a_cum
            sub_line["Reste budget"] = _remaining_budget_semantic(f_val, a_cum, row.get("nature"))
            out.append(sub_line)

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
                }
            )

    return pd.DataFrame(out)


@router.get("/preview")
def get_reporting_preview(
    target_year: int = Query(..., ge=2000, le=2100),
    cycle_code: str = Query("INITIAL"),
    month: int | None = Query(None, ge=1, le=12),
    _user: dict = Depends(require_permission("reporting", "read")),
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
            # Compatibilité descendante: certains clients envoient encore
            # les modes P&L sans activer explicitement le bloc de contenu.
            if include_pnl_selected or include_pnl_global:
                include_pnl_formatted = True
            else:
                # Fallback robuste: au moins une feuille utile au lieu d'une 400.
                include_global_state = True

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
                effective_pnl_months_selected = _resolve_pnl_months(
                    realized_months=realized_months,
                    pnl_scope="selected",
                    selected_month=selected_month,
                    pnl_months=pnl_months,
                )
            if export_pnl_global:
                effective_pnl_months_global = _resolve_pnl_months(
                    realized_months=realized_months,
                    pnl_scope="global",
                    selected_month=selected_month,
                    pnl_months=pnl_months,
                )

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
                if not key:
                    continue
                sub_ann_map[key] = list(get_subagregats(target_year, effective_budget_cycle, key, None).get("items", []))

        pnl_selected_df = pd.DataFrame()
        pnl_global_df = pd.DataFrame()

        if include_pnl_formatted:
            annual_base = get_annual_comparison(target_year=target_year, cycle_code=cycle_code)
            annual_pnl_rows = annual_base.get("rows", [])
            pnl_sub_map: dict[str, list[dict]] = {}
            for row in annual_pnl_rows:
                key = row.get("agregat_key")
                if not key or key not in PNL_KEYS:
                    continue
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
        aggregate_key_by_label = {
            str(r.get("agregat_label") or ""): str(r.get("agregat_key") or "")
            for r in annual_raw_rows
            if r.get("agregat_label") and r.get("agregat_key")
        }
        executive_rows = [
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

        global_state_df = _build_global_state_df(
            target_year=target_year,
            cycle_code=effective_budget_cycle,
            annual_rows=annual_raw_rows,
            sub_ann_map=sub_ann_map,
            realized_months=realized_months,
        ) if include_global_state else pd.DataFrame()

        executive_df = _format_df_reste_budget(executive_df)
        pnl_selected_df = _format_df_reste_budget(pnl_selected_df)
        pnl_global_df = _format_df_reste_budget(pnl_global_df)
        annual_df = _format_df_reste_budget(annual_df)
        annual_detail_df = _format_df_reste_budget(annual_detail_df)
        monthly_detail_df = _format_df_reste_budget(monthly_detail_df)
        global_state_df = _format_df_reste_budget(global_state_df)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            TITLE_ROW = 0
            HEADER_ROW = 2
            DATA_START_ROW = 3

            if include_executive_summary:
                executive_df.to_excel(writer, sheet_name="Executive_Summary", index=False, startrow=HEADER_ROW)
            if include_pnl_formatted:
                has_selected = not pnl_selected_df.empty
                has_global = not pnl_global_df.empty
                if has_selected and has_global:
                    pnl_selected_df.to_excel(writer, sheet_name="PnL_Formate_Selection", index=False, startrow=HEADER_ROW)
                    pnl_global_df.to_excel(writer, sheet_name="PnL_Formate_Global", index=False, startrow=HEADER_ROW)
                elif has_selected:
                    pnl_selected_df.to_excel(writer, sheet_name="PnL_Formate", index=False, startrow=HEADER_ROW)
                elif has_global:
                    pnl_global_df.to_excel(writer, sheet_name="PnL_Formate", index=False, startrow=HEADER_ROW)
            if include_budget_forecast:
                annual_df.to_excel(writer, sheet_name="Forecast_Annuel", index=False, startrow=HEADER_ROW)
                annual_detail_df.to_excel(writer, sheet_name="Forecast_Annuel_Detail", index=False, startrow=HEADER_ROW)
                if include_monthly_forecast:
                    monthly_detail_df.to_excel(writer, sheet_name="Forecast_Mensuel_Detail", index=False, startrow=HEADER_ROW)
            if include_global_state:
                global_state_df.to_excel(writer, sheet_name="Etat_Globale", index=False, startrow=HEADER_ROW)
            if include_cycles:
                cycles_df.to_excel(writer, sheet_name="Cycles", index=False, startrow=HEADER_ROW)
            if include_alerts:
                alerts_start_row = HEADER_ROW
                if not annual_alerts_df.empty:
                    annual_alerts_df.to_excel(writer, sheet_name="Alertes", index=False, startrow=alerts_start_row)
                    alerts_start_row += len(annual_alerts_df) + 3
                if not monthly_alerts_df.empty:
                    monthly_alerts_df.to_excel(writer, sheet_name="Alertes", index=False, startrow=alerts_start_row)

            workbook = writer.book
            money_fmt = workbook.add_format({"num_format": "#,##0.000"})
            positive_money_fmt = workbook.add_format({"num_format": "+#,##0.000;-#,##0.000;0.000"})
            pct_fmt = workbook.add_format({"num_format": "0.000"})
            header_fmt = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1E3A8A", "border": 1, "align": "center"})
            kpi_row_fmt = workbook.add_format({"bg_color": "#EEF2FF", "bold": True, "num_format": "#,##0.000"})
            aggregate_row_fmt = workbook.add_format({"bg_color": "#E0F2FE", "bold": True, "num_format": "#,##0.000"})
            aggregate_formula_fmt = workbook.add_format({"bg_color": "#E0F2FE", "bold": True, "font_color": "#000000", "num_format": "#,##0.000"})
            aggregate_pct_formula_fmt = workbook.add_format({"bg_color": "#E0F2FE", "bold": True, "font_color": "#000000", "num_format": "0.000"})
            linked_formula_fmt = workbook.add_format({"font_color": "#008000", "num_format": "#,##0.000"})
            linked_pct_formula_fmt = workbook.add_format({"font_color": "#008000", "num_format": "0.000"})
            subaggregate_row_fmt = workbook.add_format({"bg_color": "#F8FAFC", "num_format": "#,##0.000"})
            pnl_products_fmt = workbook.add_format({"bg_color": "#ECFDF5", "num_format": "#,##0.000"})
            pnl_charges_fmt = workbook.add_format({"bg_color": "#FEF2F2", "num_format": "#,##0.000"})
            pnl_result_fmt = workbook.add_format({"bg_color": "#EFF6FF", "bold": True, "num_format": "#,##0.000"})
            pnl_products_agg_fmt = workbook.add_format({"bg_color": "#ECFDF5", "bold": True, "num_format": "#,##0.000"})
            pnl_charges_agg_fmt = workbook.add_format({"bg_color": "#FEF2F2", "bold": True, "num_format": "#,##0.000"})
            pnl_result_agg_fmt = workbook.add_format({"bg_color": "#EFF6FF", "bold": True, "num_format": "#,##0.000"})
            title_fmt = workbook.add_format({
                "bold": True,
                "font_size": 13,
                "font_color": "#1E3A8A",
                "align": "left",
                "valign": "vcenter",
            })

            sheet_titles = {
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

            for sheet_name in writer.sheets.keys():
                ws = writer.sheets[sheet_name]
                df_source = None
                if sheet_name == "Executive_Summary":
                    df_source = executive_df
                elif sheet_name == "PnL_Formate":
                    df_source = pnl_selected_df if not pnl_selected_df.empty else pnl_global_df
                elif sheet_name == "PnL_Formate_Selection":
                    df_source = pnl_selected_df
                elif sheet_name == "PnL_Formate_Global":
                    df_source = pnl_global_df
                elif sheet_name == "Forecast_Annuel":
                    df_source = annual_df
                elif sheet_name == "Forecast_Annuel_Detail":
                    df_source = annual_detail_df
                elif sheet_name == "Forecast_Mensuel_Detail":
                    df_source = monthly_detail_df
                elif sheet_name == "Etat_Globale":
                    df_source = global_state_df
                elif sheet_name == "Cycles":
                    df_source = cycles_df
                elif sheet_name == "Alertes":
                    df_source = pd.concat([annual_alerts_df, monthly_alerts_df], ignore_index=True)

                if df_source is not None and not df_source.empty:
                    ws.autofilter(HEADER_ROW, 0, HEADER_ROW + len(df_source), max(len(df_source.columns) - 1, 0))

                ws.freeze_panes(DATA_START_ROW, 0)
                ws.set_row(HEADER_ROW, 22, header_fmt)
                ws.set_column(0, 0, 34)
                ws.set_column(1, 30, 18, money_fmt)

                title_text = sheet_titles.get(sheet_name)
                if title_text:
                    max_col = max((len(df_source.columns) - 1) if (df_source is not None and not df_source.empty) else 3, 3)
                    ws.merge_range(TITLE_ROW, 0, TITLE_ROW, max_col, title_text, title_fmt)

                if df_source is not None and not df_source.empty:
                    for idx, col in enumerate(df_source.columns):
                        name = str(col).lower()
                        if "taux" in name or "%" in name:
                            ws.set_column(idx, idx, 16, pct_fmt)
                        elif any(token in name for token in ["nature", "indice", "alerte", "modèle", "agrégat", "sous-agrégat", "mois"]):
                            ws.set_column(idx, idx, 28)

                    if sheet_name in {
                        "Executive_Summary",
                        "Forecast_Annuel",
                        "Forecast_Annuel_Detail",
                        "Forecast_Mensuel_Detail",
                    }:
                        _write_budget_formulas(
                            worksheet=ws,
                            dataframe=df_source,
                            data_start_row=DATA_START_ROW,
                            money_format=money_fmt,
                            positive_money_format=positive_money_fmt,
                            percent_format=pct_fmt,
                            aggregate_formula_format=aggregate_formula_fmt,
                            aggregate_percent_format=aggregate_pct_formula_fmt,
                            linked_formula_format=linked_formula_fmt,
                            linked_percent_format=linked_pct_formula_fmt,
                            sheet_name=sheet_name,
                            aggregate_key_by_label=aggregate_key_by_label,
                            annual_dataframe=annual_df,
                            annual_detail_dataframe=annual_detail_df,
                        )

                    if "statut" in [str(c).lower() for c in df_source.columns]:
                        stat_idx = [str(c).lower() for c in df_source.columns].index("statut")
                        ws.conditional_format(DATA_START_ROW, stat_idx, HEADER_ROW + len(df_source), stat_idx, {
                            "type": "text",
                            "criteria": "containing",
                            "value": "Défavorable",
                            "format": workbook.add_format({"font_color": "#991B1B", "bg_color": "#FEE2E2", "bold": True}),
                        })
                        ws.conditional_format(DATA_START_ROW, stat_idx, HEADER_ROW + len(df_source), stat_idx, {
                            "type": "text",
                            "criteria": "containing",
                            "value": "Favorable",
                            "format": workbook.add_format({"font_color": "#14532D", "bg_color": "#DCFCE7", "bold": True}),
                        })
                        ws.conditional_format(DATA_START_ROW, stat_idx, HEADER_ROW + len(df_source), stat_idx, {
                            "type": "text",
                            "criteria": "containing",
                            "value": "Neutre",
                            "format": workbook.add_format({"font_color": "#854D0E", "bg_color": "#FEF9C3", "bold": True}),
                        })

                    if sheet_name == "Executive_Summary":
                        for ridx in range(DATA_START_ROW, DATA_START_ROW + len(df_source)):
                            ws.set_row(ridx, 20, kpi_row_fmt)

                    if sheet_name in {"Forecast_Annuel_Detail", "Forecast_Mensuel_Detail", "PnL_Formate", "PnL_Formate_Selection", "PnL_Formate_Global", "Etat_Globale"}:
                        lvl_idx = [str(c).lower() for c in df_source.columns].index("niveau") if "Niveau" in df_source.columns else -1
                        lib_idx = [str(c).lower() for c in df_source.columns].index("libellé") if "Libellé" in df_source.columns else -1

                        if sheet_name in {"Forecast_Annuel_Detail", "Forecast_Mensuel_Detail"}:
                            if lvl_idx >= 0:
                                ws.set_column(lvl_idx, lvl_idx, 15)
                            if lib_idx >= 0:
                                ws.set_column(lib_idx, lib_idx, 40)
                            if "Nature" in df_source.columns:
                                nature_idx = list(df_source.columns).index("Nature")
                                ws.set_column(nature_idx, nature_idx, 14)

                        for ridx, row in enumerate(df_source.to_dict(orient="records"), start=DATA_START_ROW):
                            level = row.get("Niveau")
                            if level == "Agrégat":
                                ws.set_row(ridx, 20, aggregate_row_fmt)
                            elif level == "Sous-agrégat":
                                ws.set_row(ridx, 20, subaggregate_row_fmt)

                            if sheet_name in {"PnL_Formate", "PnL_Formate_Selection", "PnL_Formate_Global"}:
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

                if sheet_name == "Etat_Globale" and df_source is not None and not df_source.empty:
                    cols = list(df_source.columns)
                    month_indices = [i for i, c in enumerate(cols) if str(c).startswith("M")]
                    for i in month_indices:
                        ws.set_column(i, i, 12, money_fmt)
                    if "Niveau" in cols:
                        ws.set_column(cols.index("Niveau"), cols.index("Niveau"), 14)
                    if "Libellé" in cols:
                        ws.set_column(cols.index("Libellé"), cols.index("Libellé"), 36)
                    if "Nature" in cols:
                        ws.set_column(cols.index("Nature"), cols.index("Nature"), 14)
                    ws.freeze_panes(DATA_START_ROW, 4)

                if sheet_name in {"PnL_Formate", "PnL_Formate_Selection", "PnL_Formate_Global"} and df_source is not None and not df_source.empty:
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

                    ws.freeze_panes(DATA_START_ROW, 3)

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
