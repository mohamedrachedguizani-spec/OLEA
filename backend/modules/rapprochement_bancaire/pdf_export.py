from datetime import datetime
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.rapprochement_bancaire.models import ReconciliationPdfRequest


OLEA_GREEN = colors.HexColor("#4F5D2F")
OLEA_GREEN_LIGHT = colors.HexColor("#E9ECDD")
OLEA_TERRACOTTA = colors.HexColor("#B85C38")
TEXT = colors.HexColor("#27312A")
MUTED = colors.HexColor("#667085")
GRID = colors.HexColor("#D9DED5")
ROW_ALT = colors.HexColor("#F7F8F5")


def _text(value, fallback="-"):
    if value is None or value == "":
        return fallback
    return str(value)


def _money(value):
    return f"{float(value or 0):,.3f}".replace(",", " ")


def _date(value):
    return value.strftime("%d/%m/%Y") if value else "-"


def _paragraph(value, style):
    return Paragraph(escape(_text(value)), style)


def _table(title, headers, rows, widths, styles):
    title_block = Paragraph(title, styles["section"])
    if not rows:
        return [KeepTogether([
            title_block,
            Paragraph("Aucune donnée dans cette catégorie.", styles["empty"]),
            Spacer(1, 5 * mm),
        ])]

    header = [Paragraph(escape(item), styles["table_header"]) for item in headers]
    body = [[_paragraph(cell, styles["table_cell"]) for cell in row] for row in rows]
    table = Table([header, *body], colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), OLEA_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
    ]))
    return [title_block, table, Spacer(1, 6 * mm)]


def _page(canvas, doc):
    canvas.saveState()
    page_width, page_height = landscape(A4)
    canvas.setStrokeColor(OLEA_GREEN)
    canvas.setLineWidth(1)
    canvas.line(doc.leftMargin, page_height - 12 * mm, page_width - doc.rightMargin, page_height - 12 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(OLEA_GREEN)
    canvas.drawString(doc.leftMargin, page_height - 9 * mm, "OLEA - Rapprochement bancaire")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(page_width - doc.rightMargin, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_reconciliation_pdf(payload: ReconciliationPdfRequest) -> BytesIO:
    result = payload.result
    stats = result.stats
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=18 * mm,
        bottomMargin=13 * mm,
        title="Résultats du rapprochement bancaire",
        author="OLEA",
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "PdfTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=OLEA_GREEN, alignment=TA_LEFT,
            spaceAfter=3 * mm,
        ),
        "subtitle": ParagraphStyle(
            "PdfSubtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, leading=11, textColor=MUTED, spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "PdfSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, leading=14, textColor=OLEA_TERRACOTTA,
            spaceBefore=2 * mm, spaceAfter=2 * mm,
        ),
        "table_header": ParagraphStyle(
            "PdfTableHeader", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.3, leading=7.5, textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "PdfTableCell", parent=base["Normal"], fontName="Helvetica",
            fontSize=6.1, leading=7.4, textColor=TEXT,
        ),
        "summary_label": ParagraphStyle(
            "PdfSummaryLabel", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.5, leading=9, textColor=MUTED,
        ),
        "summary_value": ParagraphStyle(
            "PdfSummaryValue", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=12, textColor=TEXT,
        ),
        "empty": ParagraphStyle(
            "PdfEmpty", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, leading=10, textColor=MUTED, leftIndent=3 * mm,
        ),
    }

    generated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
    story = [
        Paragraph("Résultats du rapprochement bancaire", styles["title"]),
        Paragraph(
            f"Généré le {generated_at}<br/>Grand livre Sage : {escape(_text(payload.sage_filename))}"
            f" &nbsp;&nbsp;|&nbsp;&nbsp; Relevé bancaire : {escape(_text(payload.bank_filename))}",
            styles["subtitle"],
        ),
    ]

    summary_items = [
        ("Mouvements banque", stats.total_bank_movements),
        ("Écritures Sage", stats.total_sage_movements),
        ("Rapprochés automatiquement", stats.auto_reconciled_count),
        ("Écarts de montant", stats.discrepancies_count),
        ("Montant total des écarts", f"{_money(stats.total_discrepancy_amount)} TND"),
        ("Taux d’automatisation", f"{stats.automation_rate:.2f} %"),
    ]
    summary_data = [
        [Paragraph(escape(label), styles["summary_label"]) for label, _ in summary_items],
        [Paragraph(escape(str(value)), styles["summary_value"]) for _, value in summary_items],
    ]
    summary = Table(summary_data, colWidths=[43 * mm] * 6)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OLEA_GREEN_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.7, OLEA_GREEN),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([summary, Spacer(1, 6 * mm)])

    reconciled_rows = [[
        _date(pair.sage.date_ecriture), pair.sage.libelle_ecriture, pair.sage.reference_piece,
        _money(pair.sage.debit), _money(pair.sage.credit), _date(pair.bank.date_operation),
        pair.bank.libelle, pair.bank.reference, _money(pair.bank.debit),
        _money(pair.bank.credit),
    ] for pair in result.reconciled]
    story.extend(_table(
        f"Rapprochements validés ({len(reconciled_rows)})",
        ["Date Sage", "Libellé Sage", "Réf. Sage", "Débit", "Crédit", "Date banque", "Libellé banque", "Réf. banque", "Débit", "Crédit"],
        reconciled_rows,
        [17*mm, 45*mm, 24*mm, 19*mm, 19*mm, 17*mm, 45*mm, 24*mm, 19*mm, 19*mm],
        styles,
    ))

    story.append(PageBreak())
    discrepancy_rows = [[
        _date(pair.sage.date_ecriture), pair.sage.libelle_ecriture, pair.sage.reference_piece,
        _money(pair.sage.amount), _date(pair.bank.date_operation), pair.bank.libelle,
        pair.bank.reference, _money(pair.bank.amount), _money(pair.difference),
    ] for pair in result.discrepancies]
    story.extend(_table(
        f"Écarts de montant ({len(discrepancy_rows)})",
        ["Date Sage", "Libellé Sage", "Réf. Sage", "Montant Sage", "Date banque", "Libellé banque", "Réf. banque", "Montant banque", "Écart"],
        discrepancy_rows,
        [18*mm, 52*mm, 25*mm, 23*mm, 18*mm, 52*mm, 25*mm, 23*mm, 22*mm],
        styles,
    ))

    bank_only_rows = [[
        _date(item.date_operation), item.reference, item.libelle,
        _money(item.debit), _money(item.credit), _money(item.amount),
    ] for item in result.bank_only]
    story.extend(_table(
        f"Mouvements présents uniquement en banque ({len(bank_only_rows)})",
        ["Date", "Référence", "Libellé", "Débit", "Crédit", "Montant"],
        bank_only_rows,
        [24*mm, 35*mm, 116*mm, 30*mm, 30*mm, 30*mm],
        styles,
    ))

    sage_only_rows = [[
        _date(item.date_ecriture), item.journal, item.numero_piece,
        item.reference_piece, item.libelle_ecriture, _money(item.debit),
        _money(item.credit), _money(item.amount),
    ] for item in result.sage_only]
    story.extend(_table(
        f"Écritures présentes uniquement dans Sage ({len(sage_only_rows)})",
        ["Date", "Journal", "N° pièce", "Référence", "Libellé", "Débit", "Crédit", "Montant"],
        sage_only_rows,
        [20*mm, 18*mm, 25*mm, 30*mm, 92*mm, 25*mm, 25*mm, 25*mm],
        styles,
    ))

    document.build(story, onFirstPage=_page, onLaterPages=_page)
    buffer.seek(0)
    return buffer
