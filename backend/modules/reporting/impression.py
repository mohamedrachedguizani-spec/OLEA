import base64
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
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.auth.dependencies import require_any_permission_code, require_permission_code
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
    dependencies=[Depends(require_permission_code("reporting.read"))],
)

PDF_PRIMARY = colors.HexColor("#B4482B")
PDF_PRIMARY_LIGHT = colors.HexColor("#F8ECE8")
PDF_AMBER_LIGHT = colors.HexColor("#FFF3DD")
PDF_TEXT = colors.HexColor("#30343A")
PDF_MUTED = colors.HexColor("#667085")
PDF_GRID = colors.HexColor("#E1E3E5")
PDF_SUB = colors.HexColor("#F8F8F7")
PDF_PRODUCT = colors.HexColor("#FFF8EA")
PDF_CHARGE = colors.HexColor("#FCEBE6")
PDF_RESULT = colors.HexColor("#F8ECE8")
PDF_LOGO_PATH = Path(__file__).resolve().parents[1] / "rapprochement_bancaire" / "olea-logo.png"


def _logo_data_uri() -> str:
    """Embed the shared OLEA logo so browser printing remains self-contained."""
    if not PDF_LOGO_PATH.is_file():
        return ""
    encoded = base64.b64encode(PDF_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


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
    generated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
    logo_uri = _logo_data_uri()
    logo = (
        f'<img class="logo" src="{logo_uri}" alt="OLEA" />'
        if logo_uri
        else '<div class="logo-fallback">OLEA</div>'
    )
    sections = []
    for sheet_name, df in frames:
        title = title_map.get(sheet_name, sheet_name)
        sections.append(
            f"""
            <section class=\"sheet\">
                <header class=\"print-header\">
                    {logo}
                    <span>REPORTING DÉCISIONNEL</span>
                </header>
                <div class=\"report-heading\">
                    <div>
                        <div class=\"eyebrow\">RAPPORT DE PILOTAGE</div>
                        <h1>Reporting décisionnel</h1>
                    </div>
                    <div class=\"meta-grid\">
                        <div><small>EXERCICE</small><strong>{year}</strong></div>
                        <div><small>CYCLE</small><strong>{html.escape(str(cycle_code))}</strong></div>
                        <div><small>ÉDITÉ LE</small><strong>{generated_at}</strong></div>
                    </div>
                </div>
                <h2>{html.escape(title)}</h2>
                {_table_html(df, sheet_name)}
                <footer>Document généré par OLEA Finance</footer>
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
    body {{ margin: 0; font-family: Arial, sans-serif; color: #30343a; background: #fff; }}
    .sheet {{ position: relative; min-height: 178mm; page-break-after: always; padding-bottom: 8mm; }}
    .sheet:last-child {{ page-break-after: auto; }}
    .print-header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #b4482b; padding-bottom: 7px; margin-bottom: 14px; }}
    .print-header span {{ color: #30343a; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; }}
    .logo {{ display: block; width: 96px; height: auto; max-height: 44px; object-fit: contain; }}
    .logo-fallback {{ color: #b4482b; font-size: 22px; font-weight: 800; }}
    .report-heading {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 17px; }}
    .eyebrow {{ color: #b4482b; font-size: 9px; font-weight: 700; letter-spacing: 1.15px; margin-bottom: 3px; }}
    h1 {{ margin: 0; color: #30343a; font-size: 22px; line-height: 1.2; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(3, minmax(92px, auto)); background: #f8ece8; border-top: 3px solid #b4482b; }}
    .meta-grid > div {{ display: flex; flex-direction: column; padding: 7px 10px; border-left: 1px solid #e5c9c0; }}
    .meta-grid > div:first-child {{ border-left: 0; }}
    .meta-grid small {{ color: #667085; font-size: 8px; font-weight: 700; letter-spacing: .55px; }}
    .meta-grid strong {{ margin-top: 2px; font-size: 10px; white-space: nowrap; }}
    h2 {{ margin: 0 0 9px; color: #b4482b; font-size: 15px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
    th {{ background: #b4482b; color: #fff; border: 1px solid #b4482b; padding: 7px 6px; text-align: left; font-size: 9px; letter-spacing: .25px; }}
    td {{ border: 1px solid #e1e3e5; padding: 6px; }}
    tbody tr:nth-child(even) td {{ background: #fbfbfa; }}
    .row-kpi td, .row-result td {{ background: #f8ece8 !important; font-weight: 700; }}
    .row-agg td {{ background: #fff3dd !important; font-weight: 700; }}
    .row-sub td {{ background: #f8f8f7 !important; }}
    .row-produit td {{ background: #fff8ea !important; }}
    .row-charge td {{ background: #fcebe6 !important; }}
    .empty {{ color: #667085; font-style: italic; padding: 8px 0; }}
    footer {{ position: absolute; bottom: 0; left: 0; right: 0; border-top: 1px solid #e1e3e5; padding-top: 5px; color: #667085; font-size: 8px; }}
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
        if PDF_ARROW_FONT:
            text = text.replace("↳", f'<font name="{PDF_ARROW_FONT}">↳</font>')
        else:
            # Le PDF doit rester exportable sur les serveurs dépourvus de
            # police Unicode. Le chevron ASCII conserve le niveau visuel.
            text = text.replace("↳", "&gt;")
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
    if PDF_LOGO_PATH.is_file():
        canvas.drawImage(
            ImageReader(str(PDF_LOGO_PATH)),
            document.leftMargin,
            page_height - 19 * mm,
            width=31 * mm,
            height=13.3 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        canvas.setFont("Helvetica-Bold", 15)
        canvas.setFillColor(PDF_PRIMARY)
        canvas.drawString(document.leftMargin, page_height - 13 * mm, "OLEA")
    canvas.setStrokeColor(PDF_PRIMARY)
    canvas.setLineWidth(1.2)
    canvas.line(document.leftMargin, page_height - 21 * mm, page_width - document.rightMargin, page_height - 21 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(PDF_TEXT)
    canvas.drawRightString(page_width - document.rightMargin, page_height - 13 * mm, "REPORTING DÉCISIONNEL")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(PDF_MUTED)
    canvas.drawString(document.leftMargin, 7 * mm, "Document généré par OLEA Finance")
    canvas.drawRightString(page_width - document.rightMargin, 7 * mm, f"Page {document.page}")
    canvas.restoreState()


def _build_reporting_pdf(sections: list[dict], year: int, cycle_code: str) -> BytesIO:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=27 * mm,
        bottomMargin=13 * mm,
        title=f"Reporting OLEA {year}",
        author="OLEA",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportingPdfTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, alignment=TA_LEFT, textColor=PDF_TEXT, spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "ReportingPdfSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, leading=14, textColor=PDF_PRIMARY, spaceAfter=3 * mm,
        ),
        "empty": ParagraphStyle(
            "ReportingPdfEmpty", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=PDF_MUTED,
        ),
    }
    generated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
    meta_label = ParagraphStyle(
        "ReportingPdfMetaLabel", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=6.5, leading=8, textColor=PDF_MUTED,
    )
    meta_value = ParagraphStyle(
        "ReportingPdfMetaValue", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=8.5, leading=10, textColor=PDF_TEXT,
    )
    meta_table = Table(
        [
            [Paragraph("EXERCICE", meta_label), Paragraph("CYCLE", meta_label),
             Paragraph("DATE D'ÉDITION", meta_label), Paragraph("SECTIONS", meta_label)],
            [Paragraph(str(year), meta_value), Paragraph(html.escape(str(cycle_code)), meta_value),
             Paragraph(generated_at, meta_value), Paragraph(str(len(sections)), meta_value)],
        ],
        colWidths=[65 * mm] * 4,
        hAlign="LEFT",
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PDF_PRIMARY_LIGHT),
        ("LINEABOVE", (0, 0), (-1, 0), 2, PDF_PRIMARY),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, colors.HexColor("#E5C9C0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]))
    story = [Paragraph("Reporting décisionnel", styles["title"]), meta_table, Spacer(1, 6 * mm)]
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
            ("BACKGROUND", (0, 0), (-1, 0), PDF_PRIMARY),
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
            "row-agg": PDF_AMBER_LIGHT,
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
    _user: dict = Depends(require_permission_code("reporting.print")),
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
    _user: dict = Depends(require_any_permission_code(
        "reporting.export_pdf", "reporting.export_excel", "reporting.print"
    )),
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

        return {
            "sections": sections,
            "target_year": target_year,
            "cycle_code": effective_budget_cycle,
            "generated_at": datetime.now().strftime("%d/%m/%Y à %H:%M"),
        }
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
    _user: dict = Depends(require_permission_code("reporting.export_pdf")),
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
