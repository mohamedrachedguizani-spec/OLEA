from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.rapprochement_bancaire.models import ReconciliationPdfRequest


OLEA_TERRACOTTA = colors.HexColor("#B4482B")
OLEA_TERRACOTTA_LIGHT = colors.HexColor("#F8ECE8")
OLEA_AMBER = colors.HexColor("#F5AC3B")
TEXT = colors.HexColor("#30343A")
MUTED = colors.HexColor("#667085")
GRID = colors.HexColor("#E1E3E5")
ROW_ALT = colors.HexColor("#F8F8F7")
LOGO_PATH = Path(__file__).with_name("olea-logo.png")


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
        ("BACKGROUND", (0, 0), (-1, 0), OLEA_TERRACOTTA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
    ]))
    # Keep the section heading attached to at least the beginning of its table.
    # ReportLab can still split long tables across subsequent pages.
    return [KeepTogether([title_block, table]), Spacer(1, 6 * mm)]


def _unmatched_statement(result, context, sage_closing, bank_closing, period_end, styles):
    """Présente le rapprochement selon les conventions débit/crédit des deux sources."""
    accounting_debit = max(sage_closing or 0, 0)
    accounting_credit = max(-(sage_closing or 0), 0)
    bank_debit = max(-(bank_closing or 0), 0)
    bank_credit = max(bank_closing or 0, 0)

    data = [
        [
            Paragraph("ÉLÉMENTS", styles["statement_side"]),
            Paragraph("OPÉRATIONS COMPTABLES (SAGE)", styles["statement_side"]), "",
            Paragraph("RELEVÉ BANCAIRE", styles["statement_side"]), "",
        ],
        [
            "", Paragraph("Débit (+)", styles["table_header"]),
            Paragraph("Crédit (-)", styles["table_header"]),
            Paragraph("Débit (-)", styles["table_header"]),
            Paragraph("Crédit (+)", styles["table_header"]),
        ],
        [
            Paragraph(f"Soldes au {_date(period_end)}", styles["statement_total"]),
            _paragraph(_money(accounting_debit), styles["statement_amount"]) if accounting_debit else "",
            _paragraph(_money(accounting_credit), styles["statement_amount"]) if accounting_credit else "",
            _paragraph(_money(bank_debit), styles["statement_amount"]) if bank_debit else "",
            _paragraph(_money(bank_credit), styles["statement_amount"]) if bank_credit else "",
        ],
    ]

    # Les mouvements banque absents de SAGE corrigent le solde comptable.
    for item in result.bank_only:
        if item.amount >= 0:
            accounting_debit += item.amount
        else:
            accounting_credit += abs(item.amount)
        data.append([
            _paragraph(
                f"{_date(item.date_operation)} - {item.reference or 'Sans référence'} - {item.libelle}",
                styles["table_cell"],
            ),
            _paragraph(_money(item.amount), styles["statement_amount"]) if item.amount > 0 else "",
            _paragraph(_money(abs(item.amount)), styles["statement_amount"]) if item.amount < 0 else "",
            "", "",
        ])

    # Les écritures SAGE absentes du relevé corrigent le solde bancaire.
    for item in result.sage_only:
        if item.amount >= 0:
            bank_credit += item.amount
        else:
            bank_debit += abs(item.amount)
        data.append([
            _paragraph(
                f"{_date(item.date_ecriture)} - {item.reference_piece or item.numero_piece} - {item.libelle_ecriture}",
                styles["table_cell"],
            ),
            "", "",
            _paragraph(_money(abs(item.amount)), styles["statement_amount"]) if item.amount < 0 else "",
            _paragraph(_money(item.amount), styles["statement_amount"]) if item.amount > 0 else "",
        ])

    total_row = len(data)
    data.append([
        Paragraph("Totaux partiels", styles["statement_total"]),
        _paragraph(_money(accounting_debit), styles["statement_amount"]),
        _paragraph(_money(accounting_credit), styles["statement_amount"]),
        _paragraph(_money(bank_debit), styles["statement_amount"]),
        _paragraph(_money(bank_credit), styles["statement_amount"]),
    ])

    adjusted_sage = context.adjusted_sage_balance
    adjusted_bank = context.adjusted_bank_balance
    if adjusted_sage is None and sage_closing is not None:
        adjusted_sage = accounting_debit - accounting_credit
    if adjusted_bank is None and bank_closing is not None:
        adjusted_bank = bank_credit - bank_debit
    reconciled_row = len(data)
    sage_debit = adjusted_sage if adjusted_sage is not None and adjusted_sage >= 0 else None
    sage_credit = abs(adjusted_sage) if adjusted_sage is not None and adjusted_sage < 0 else None
    statement_bank_debit = abs(adjusted_bank) if adjusted_bank is not None and adjusted_bank < 0 else None
    statement_bank_credit = adjusted_bank if adjusted_bank is not None and adjusted_bank >= 0 else None
    data.append([
        Paragraph("Solde rapproché", styles["statement_total"]),
        _paragraph(_money(sage_debit), styles["statement_amount"]) if sage_debit is not None else "",
        _paragraph(_money(sage_credit), styles["statement_amount"]) if sage_credit is not None else "",
        _paragraph(_money(statement_bank_debit), styles["statement_amount"]) if statement_bank_debit is not None else "",
        _paragraph(_money(statement_bank_credit), styles["statement_amount"]) if statement_bank_credit is not None else "",
    ])

    table = Table(data, colWidths=[125*mm, 34*mm, 34*mm, 34*mm, 34*mm], repeatRows=2, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("SPAN", (1, 0), (2, 0)), ("SPAN", (3, 0), (4, 0)),
        ("BACKGROUND", (0, 0), (2, 0), OLEA_TERRACOTTA_LIGHT),
        ("BACKGROUND", (3, 0), (4, 0), colors.HexColor("#FFF3DD")),
        ("BACKGROUND", (0, 1), (-1, 1), OLEA_TERRACOTTA),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
        ("BACKGROUND", (0, 2), (-1, 2), ROW_ALT),
        ("BACKGROUND", (0, total_row), (-1, total_row), ROW_ALT),
        ("BACKGROUND", (0, reconciled_row), (-1, reconciled_row), OLEA_TERRACOTTA_LIGHT),
        ("LINEBEFORE", (3, 0), (3, -1), 1.2, OLEA_AMBER),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, OLEA_TERRACOTTA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 3), (-1, total_row - 1), [colors.white, ROW_ALT]),
    ]))

    residual = None if adjusted_sage is None or adjusted_bank is None else adjusted_sage - adjusted_bank
    discrepancy_note = f" {len(result.discrepancies)} écart(s) de montant restent à valider." if result.discrepancies else ""
    if residual is not None and abs(residual) <= 0.01 and not result.discrepancies:
        note = f"Les deux soldes ajustés sont identiques à {_money(adjusted_sage)} TND. Le rapprochement est équilibré."
        note_style = styles["statement_success"]
    elif residual is not None:
        note = f"Écart résiduel à justifier : {_money(abs(residual))} TND.{discrepancy_note}"
        note_style = styles["statement_warning"]
    else:
        note = "Le solde rapproché ne peut pas être calculé : un solde de départ est manquant."
        note_style = styles["statement_warning"]

    return [
        Paragraph("Tableau de l'état de rapprochement", styles["section"]),
        table,
        Spacer(1, 2.5 * mm),
        Paragraph(note, note_style),
        Spacer(1, 6 * mm),
    ]


def _page(canvas, doc):
    canvas.saveState()
    page_width, page_height = landscape(A4)
    if LOGO_PATH.exists():
        canvas.drawImage(
            ImageReader(str(LOGO_PATH)), doc.leftMargin, page_height - 19 * mm,
            width=31 * mm, height=13.3 * mm, preserveAspectRatio=True, mask="auto",
        )
    canvas.setStrokeColor(OLEA_TERRACOTTA)
    canvas.setLineWidth(1.2)
    canvas.line(doc.leftMargin, page_height - 21 * mm, page_width - doc.rightMargin, page_height - 21 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(TEXT)
    canvas.drawRightString(page_width - doc.rightMargin, page_height - 13 * mm, "RAPPROCHEMENT BANCAIRE")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 7 * mm, "Document généré par OLEA Finance")
    canvas.drawRightString(page_width - doc.rightMargin, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_reconciliation_pdf(payload: ReconciliationPdfRequest) -> BytesIO:
    result = payload.result
    stats = result.stats
    context = result.context
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=27 * mm,
        bottomMargin=13 * mm,
        title="Résultats du rapprochement bancaire",
        author="OLEA",
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "PdfTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=TEXT, alignment=TA_LEFT,
            spaceAfter=3 * mm,
        ),
        "subtitle": ParagraphStyle(
            "PdfSubtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, leading=11, textColor=MUTED, spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "PdfSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=10.5, leading=14, textColor=OLEA_TERRACOTTA,
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
        "context_label": ParagraphStyle(
            "PdfContextLabel", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7, leading=9, textColor=MUTED,
        ),
        "context_value": ParagraphStyle(
            "PdfContextValue", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=10, textColor=TEXT,
        ),
        "document_ref": ParagraphStyle(
            "PdfDocumentRef", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7, leading=9, textColor=OLEA_TERRACOTTA,
        ),
        "statement_side": ParagraphStyle(
            "PdfStatementSide", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.2, leading=9, textColor=TEXT,
        ),
        "statement_total": ParagraphStyle(
            "PdfStatementTotal", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.4, leading=8, textColor=TEXT,
        ),
        "statement_amount": ParagraphStyle(
            "PdfStatementAmount", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.4, leading=8, textColor=TEXT, alignment=2,
        ),
        "statement_success": ParagraphStyle(
            "PdfStatementSuccess", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, leading=11, textColor=colors.HexColor("#25714A"),
            leftIndent=2 * mm,
        ),
        "statement_warning": ParagraphStyle(
            "PdfStatementWarning", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, leading=11, textColor=OLEA_TERRACOTTA,
            leftIndent=2 * mm,
        ),
    }

    generated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
    story = [
        Paragraph("Rapport de rapprochement bancaire", styles["title"]),
        Paragraph(
            f"RAPPORT DE CONTRÔLE · ÉDITÉ LE {generated_at.upper()}",
            styles["document_ref"],
        ),
        Spacer(1, 3 * mm),
    ]

    if context:
        context_data = [
            [
                Paragraph("Compte bancaire (journal)", styles["context_label"]),
                Paragraph("Compte comptable", styles["context_label"]),
                Paragraph("Période", styles["context_label"]),
                Paragraph("Date de rapprochement", styles["context_label"]),
            ],
            [
                Paragraph(escape(context.bank_journal), styles["context_value"]),
                Paragraph(escape(context.account_code), styles["context_value"]),
                Paragraph(f"{_date(context.period_start)} au {_date(context.period_end)}", styles["context_value"]),
                Paragraph(generated_at, styles["context_value"]),
            ],
        ]
        context_table = Table(context_data, colWidths=[65 * mm] * 4)
        context_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), OLEA_TERRACOTTA_LIGHT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, GRID),
            ("LINEBEFORE", (1, 0), (-1, -1), 0.35, GRID),
            ("LINEABOVE", (0, 0), (-1, 0), 1.2, OLEA_TERRACOTTA),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([context_table, Spacer(1, 2.5 * mm)])

    story.append(Paragraph(
        f"Grand livre Sage : {escape(_text(payload.sage_filename))}"
        f" &nbsp;&nbsp;|&nbsp;&nbsp; Relevé bancaire : {escape(_text(payload.bank_filename))}",
        styles["subtitle"],
    ))

    if context:
        sage_opening = context.sage_opening.amount
        bank_opening = context.bank_opening.amount
        sage_closing = None if sage_opening is None else sage_opening + stats.sage_total_debit - stats.sage_total_credit
        bank_closing = None if bank_opening is None else bank_opening + stats.bank_total_credit - stats.bank_total_debit
        status_label = {
            "conforme": "Conforme",
            "ecart": "Écart à vérifier",
            "unverifiable": "Non vérifiable",
        }.get(context.opening_status, context.opening_status)
        balance_rows = [
            ["Solde initial SAGE", _money(sage_opening) if sage_opening is not None else "Non détecté"],
            ["Solde de départ banque", _money(bank_opening) if bank_opening is not None else "Non détecté"],
            ["Écart initial (Banque - SAGE)", _money(context.opening_difference) if context.opening_difference is not None else "Non calculable"],
            ["Statut du contrôle initial", status_label],
        ]
        balance_table = Table(
            [[Paragraph(escape(label), styles["table_cell"]), Paragraph(escape(str(value)), styles["context_value"])] for label, value in balance_rows],
            colWidths=[90 * mm, 45 * mm],
            hAlign="LEFT",
        )
        balance_table.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, ROW_ALT]),
            ("LINEBELOW", (0, 0), (-1, -2), 0.35, GRID),
            ("LINEBEFORE", (1, 0), (1, -1), 0.35, GRID),
            ("LINEABOVE", (0, 0), (-1, 0), 1.2, OLEA_TERRACOTTA),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([
            Paragraph("Contrôle des soldes de départ", styles["section"]),
            balance_table,
            Spacer(1, 5 * mm),
        ])

    if context:
        story.extend(_unmatched_statement(
            result, context, sage_closing, bank_closing, context.period_end, styles
        ))

    discrepancy_rows = [[
        _date(pair.sage.date_ecriture), pair.sage.libelle_ecriture, pair.sage.reference_piece,
        _money(pair.sage.amount), _date(pair.bank.date_operation), pair.bank.libelle,
        pair.bank.reference, _money(pair.bank.amount), _money(pair.difference),
    ] for pair in result.discrepancies]
    if discrepancy_rows:
        story.extend(_table(
            f"Écarts de montant ({len(discrepancy_rows)})",
            ["Date Sage", "Libellé Sage", "Réf. Sage", "Montant Sage", "Date banque", "Libellé banque", "Réf. banque", "Montant banque", "Écart"],
            discrepancy_rows,
            [18*mm, 52*mm, 25*mm, 23*mm, 18*mm, 52*mm, 25*mm, 23*mm, 22*mm],
            styles,
        ))


    document.build(story, onFirstPage=_page, onLaterPages=_page)
    buffer.seek(0)
    return buffer
