import html
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from modules.auth.dependencies import get_current_user, require_permission
from modules.forecast.engine import get_annual_comparison, get_comparison, get_cycle_status, get_subagregats
from .router import (
    _build_annual_forecast_export_rows,
    _build_global_state_df,
    _build_hierarchical_annual_df,
    _build_hierarchical_monthly_detail_df,
    _build_pnl_formatted_hierarchical_df,
    _format_df_reste_budget,
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

PDF_BLUE = colors.HexColor("#1E3A8A")
PDF_BLUE_LIGHT = colors.HexColor("#E0F2FE")
PDF_TEXT = colors.HexColor("#0F172A")
PDF_MUTED = colors.HexColor("#64748B")
PDF_GRID = colors.HexColor("#CBD5E1")
PDF_SUB = colors.HexColor("#F8FAFC")
PDF_PRODUCT = colors.HexColor("#ECFDF5")
PDF_CHARGE = colors.HexColor("#FEF2F2")
PDF_RESULT = colors.HexColor("#EFF6FF")


def _register_pdf_arrow_font() -> str | None:
    candidates = [
        Path("C:/Windows/Fonts/seguisym.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    for font_path in candidates:
        if not font_path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("OLEAUnicode", str(font_path)))
            return "OLEAUnicode"
        except Exception:
            continue
    return None


PDF_ARROW_FONT = _register_pdf_arrow_font()


def _row_is_product(row: dict) -> bool:
    nature = str(row.get("Nature") or "").lower().strip()
    if nature == "produit":
        return True
    if nature == "charge":
        return False
    
    lib = str(row.get("Libellé") or row.get("KPI") or "").lower().strip()
    lib = lib.replace("↳", "").strip()
    
    product_indicators = [
        "ca net", "ebitda", "resultat net", "résultat net", "ca brut", 
        "autres produits", "produits financiers", "produits exceptionnels",
        "profit avant impot", "profit avant impôt"
    ]
    return any(ind in lib for ind in product_indicators)


def _fmt_cell_custom(value, col_name: str, row: dict) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "0,000"
    
    try:
        val_float = float(value)
    except (ValueError, TypeError):
        return str(value)
        
    if col_name == "Reste budget" and _row_is_product(row):
        forecast_val = row.get("Prévision annuelle")
        if forecast_val is None:
            forecast_val = row.get("Prévision Annuelle")
            
        actual_val = row.get("Réalisé cumulé")
        if actual_val is None:
            actual_val = row.get("Réalisé Cumulé")
            
        if forecast_val is not None and actual_val is not None:
            try:
                f_float = float(forecast_val)
                a_float = float(actual_val)
                
                is_exceeded = (
                    a_float > f_float if f_float >= 0 else a_float < f_float
                )
                if is_exceeded and val_float > 0:
                    formatted = f"{val_float:,.3f}".replace(",", " ").replace(".", ",")
                    return f"+{formatted}"
            except (ValueError, TypeError):
                pass
                
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
        tds = "".join(f"<td>{html.escape(_fmt_cell_custom(row.get(c), c, row))}</td>" for c in cols)
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


def _pdf_safe_text(value) -> str:
    text = str(value if value not in (None, "") else "-")
    return (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("‑", "-")
        .replace("\u00a0", " ")
    )


def _pdf_paragraph(value, style):
    text = html.escape(_pdf_safe_text(value))
    if "↳" in text:
        if not PDF_ARROW_FONT:
            raise RuntimeError("Police Unicode requise pour afficher la hiérarchie des sous-agrégats (↳)")
        text = text.replace("↳", f'<font name="{PDF_ARROW_FONT}">↳</font>')
    return Paragraph(text, style)


def _pdf_column_widths(headers: list[str], rows: list[list[str]], available_width: float) -> list[float]:
    weights = []
    for index, header in enumerate(headers):
        lengths = [len(str(header))]
        lengths.extend(len(str(row[index])) for row in rows[:120] if index < len(row))
        weights.append(min(max(max(lengths, default=8), 8), 34))
    total = sum(weights) or 1
    return [available_width * weight / total for weight in weights]


def _reporting_pdf_page(canvas, document):
    page_width, page_height = landscape(A4)
    canvas.saveState()
    canvas.setStrokeColor(PDF_BLUE)
    canvas.setLineWidth(0.8)
    canvas.line(document.leftMargin, page_height - 11 * mm, page_width - document.rightMargin, page_height - 11 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(PDF_BLUE)
    canvas.drawString(document.leftMargin, page_height - 8 * mm, "OLEA - Reporting décisionnel")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(PDF_MUTED)
    canvas.drawRightString(page_width - document.rightMargin, 7 * mm, f"Page {document.page}")
    canvas.restoreState()


def _build_reporting_pdf(sections: list[dict], year: int, cycle_code: str) -> BytesIO:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=16 * mm,
        bottomMargin=12 * mm,
        title=f"Reporting OLEA {year}",
        author="OLEA",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportingPdfTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=17, leading=21, alignment=TA_LEFT, textColor=PDF_BLUE, spaceAfter=2 * mm,
        ),
        "meta": ParagraphStyle(
            "ReportingPdfMeta", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, leading=10, textColor=PDF_MUTED, spaceAfter=5 * mm,
        ),
        "section": ParagraphStyle(
            "ReportingPdfSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=PDF_BLUE, spaceAfter=3 * mm,
        ),
        "empty": ParagraphStyle(
            "ReportingPdfEmpty", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=PDF_MUTED,
        ),
    }
    generated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
    story = [
        Paragraph("Reporting décisionnel", styles["title"]),
        Paragraph(
            f"Exercice {year} &nbsp;&nbsp;|&nbsp;&nbsp; Cycle {html.escape(str(cycle_code))}"
            f" &nbsp;&nbsp;|&nbsp;&nbsp; Généré le {generated_at}",
            styles["meta"],
        ),
    ]
    available_width = landscape(A4)[0] - document.leftMargin - document.rightMargin

    for section_index, section in enumerate(sections):
        if section_index:
            story.append(PageBreak())
        story.append(Paragraph(html.escape(_pdf_safe_text(section.get("title") or "Section")), styles["section"]))
        headers = [str(value) for value in section.get("headers") or []]
        rows = [[str(value) for value in row] for row in section.get("rows") or []]
        if not headers:
            story.append(Paragraph("Aucune donnée", styles["empty"]))
            continue

        column_count = len(headers)
        font_size = 6.6 if column_count <= 6 else 5.4 if column_count <= 10 else 4.2
        leading = font_size + 1.2
        header_style = ParagraphStyle(
            f"ReportingPdfHeader{section_index}", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=font_size, leading=leading, textColor=colors.white,
        )
        cell_style = ParagraphStyle(
            f"ReportingPdfCell{section_index}", parent=base["Normal"],
            fontName="Helvetica", fontSize=font_size, leading=leading, textColor=PDF_TEXT,
        )
        table_data = [
            [_pdf_paragraph(value, header_style) for value in headers],
            *[[_pdf_paragraph(value, cell_style) for value in row] for row in rows],
        ]
        table = LongTable(
            table_data,
            colWidths=_pdf_column_widths(headers, rows, available_width),
            repeatRows=1,
            hAlign="LEFT",
        )
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), PDF_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, PDF_GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PDF_SUB]),
        ]
        row_colors = {
            "row-kpi": PDF_RESULT,
            "row-agg": PDF_BLUE_LIGHT,
            "row-sub": PDF_SUB,
            "row-produit": PDF_PRODUCT,
            "row-charge": PDF_CHARGE,
            "row-result": PDF_RESULT,
        }
        for row_index, row_class in enumerate(section.get("row_classes") or [], start=1):
            color = row_colors.get(row_class)
            if color:
                commands.append(("BACKGROUND", (0, row_index), (-1, row_index), color))
            if row_class in {"row-kpi", "row-agg", "row-result"}:
                commands.append(("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold"))
        table.setStyle(TableStyle(commands))
        story.extend([table, Spacer(1, 3 * mm)])

    document.build(story, onFirstPage=_reporting_pdf_page, onLaterPages=_reporting_pdf_page)
    buffer.seek(0)
    return buffer


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


def _df_to_section(df: pd.DataFrame, sheet_name: str, title: str) -> dict:
    if df is None or df.empty:
        return {"title": title, "sheet_name": sheet_name, "headers": [], "rows": [], "row_classes": []}

    cols = list(df.columns)
    headers = [str(c) for c in cols]
    rows = []
    row_classes = []
    for record in df.to_dict(orient="records"):
        row_classes.append(_row_class(sheet_name, record))
        rows.append([_fmt_cell_custom(record.get(c), c, record) for c in cols])
    return {"title": title, "sheet_name": sheet_name, "headers": headers, "rows": rows, "row_classes": row_classes}


@router.get("/preview/sections")
def preview_reporting_sections(
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

        executive_df = _format_df_reste_budget(executive_df)
        pnl_selected_df = _format_df_reste_budget(pnl_selected_df)
        pnl_global_df = _format_df_reste_budget(pnl_global_df)
        annual_df = _format_df_reste_budget(annual_df)
        annual_detail_df = _format_df_reste_budget(annual_detail_df)
        monthly_detail_df = _format_df_reste_budget(monthly_detail_df)
        global_state_df = _format_df_reste_budget(global_state_df)

        title_map = {
            "Executive_Summary": "Executive Summary",
            "PnL_Formate": "P&L Formaté",
            "PnL_Formate_Selection": "P&L Formaté (Mois sélectionnés)",
            "PnL_Formate_Global": "P&L Formaté (Global)",
            "Forecast_Annuel": "Prévision Budget Annuelle",
            "Forecast_Annuel_Detail": "Prévision Budget Annuelle Détaillée",
            "Forecast_Mensuel_Detail": "Prévision Budget Mensuelle Détaillée",
            "Etat_Globale": "État Globale",
            "Cycles": "Statut des Cycles",
            "Alertes": "Alertes",
        }

        sections = []
        if include_executive_summary:
            sections.append(_df_to_section(executive_df, "Executive_Summary", title_map["Executive_Summary"]))
        if include_pnl_formatted:
            has_selected = not pnl_selected_df.empty
            has_global = not pnl_global_df.empty
            if has_selected and has_global:
                sections.append(_df_to_section(pnl_selected_df, "PnL_Formate_Selection", title_map["PnL_Formate_Selection"]))
                sections.append(_df_to_section(pnl_global_df, "PnL_Formate_Global", title_map["PnL_Formate_Global"]))
            elif has_selected:
                sections.append(_df_to_section(pnl_selected_df, "PnL_Formate", title_map["PnL_Formate"]))
            elif has_global:
                sections.append(_df_to_section(pnl_global_df, "PnL_Formate", title_map["PnL_Formate"]))
        if include_budget_forecast:
            sections.append(_df_to_section(annual_df, "Forecast_Annuel", title_map["Forecast_Annuel"]))
            sections.append(_df_to_section(annual_detail_df, "Forecast_Annuel_Detail", title_map["Forecast_Annuel_Detail"]))
            if include_monthly_forecast:
                sections.append(_df_to_section(monthly_detail_df, "Forecast_Mensuel_Detail", title_map["Forecast_Mensuel_Detail"]))
        if include_global_state:
            sections.append(_df_to_section(global_state_df, "Etat_Globale", title_map["Etat_Globale"]))
        if include_cycles:
            sections.append(_df_to_section(cycles_df, "Cycles", title_map["Cycles"]))
        if include_alerts:
            alerts_df = pd.concat([annual_alerts_df, monthly_alerts_df], ignore_index=True)
            sections.append(_df_to_section(alerts_df, "Alertes", title_map["Alertes"]))

        return {"sections": sections, "target_year": target_year, "cycle_code": effective_budget_cycle}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur preview sections reporting: {str(e)}")


@router.get("/export/pdf")
def export_reporting_pdf(
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
        preview = preview_reporting_sections(
            target_year=target_year,
            cycle_code=cycle_code,
            budget_cycle_code=budget_cycle_code,
            month=month,
            pnl_scope=pnl_scope,
            pnl_months=pnl_months,
            monthly_detail_months=monthly_detail_months,
            include_executive_summary=include_executive_summary,
            include_pnl_formatted=include_pnl_formatted,
            include_budget_forecast=include_budget_forecast,
            include_monthly_forecast=include_monthly_forecast,
            include_cycles=include_cycles,
            include_alerts=include_alerts,
            include_subaggregates=include_subaggregates,
            include_global_state=include_global_state,
            include_pnl_selected=include_pnl_selected,
            include_pnl_global=include_pnl_global,
            _user=_user,
        )
        effective_cycle = budget_cycle_code or cycle_code
        output = _build_reporting_pdf(preview.get("sections", []), target_year, effective_cycle)
        selected_month = _normalize_month_param(target_year, month)
        filename = f"Reporting_OLEA_{target_year}_{effective_cycle}_M{selected_month:02d}.pdf"
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur export reporting PDF: {str(e)}")
