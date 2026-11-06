# modules/tresorerie/pdf_export.py
"""
Génération du rapport PDF du reporting de trésorerie.
Même charte graphique que les autres modules OLEA (rapprochement bancaire,
balance âgée) : entête terracotta, logo OLEA, tableau par banque.
"""
from datetime import date, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette OLEA (alignée sur les couleurs officielles du logo OLEA) ────────────
OLEA_TERRACOTTA       = colors.HexColor("#B4482B")  # Terracotta OLEA principal
OLEA_TERRACOTTA_DARK  = colors.HexColor("#93371E")  # Terracotta sombre pour accent
OLEA_TERRACOTTA_LIGHT = colors.HexColor("#F8ECE8")  # Fond rosé très doux
OLEA_AMBER            = colors.HexColor("#E09127")  # Ambre / Ocre OLEA (2ème couleur logo)
OLEA_AMBER_LIGHT      = colors.HexColor("#FFF3DD")  # Fond ambre clair
OLEA_ANTHRACITE       = colors.HexColor("#2B2E33")  # Gris anthracite texte / logo
TEXT                  = colors.HexColor("#30343A")
MUTED                 = colors.HexColor("#667085")
GRID                  = colors.HexColor("#E1E3E5")
ROW_ALT               = colors.HexColor("#F8F8F7")
ROW_TOTAL             = colors.HexColor("#F8ECE8")  # Rappel terracotta light sur total

# Le logo est partagé avec le rapprochement bancaire : une seule copie dans le dépôt.
LOGO_PATH = Path(__file__).resolve().parents[1] / "rapprochement_bancaire" / "olea-logo.png"

NBSP = "\u00a0"  # espace insécable : séparateur de milliers imprimable en WinAnsi


# ── Helpers ───────────────────────────────────────────────────────────────────

def _text(value, fallback="—"):
    if value is None or value == "":
        return fallback
    return str(value)


def _money(value, fallback="n.d."):
    """Montant au format fran\u00e7ais (espace ins\u00e9cable + virgule d\u00e9cimale), comme l'\u00e9cran."""
    if value is None:
        return fallback
    try:
        return f"{float(value):,.3f}".replace(",", NBSP).replace(".", ",")
    except (TypeError, ValueError):
        return fallback


def _decimal(value) -> str:
    """\u00c9cart au format fran\u00e7ais sans s\u00e9parateur de milliers (notes de contr\u00f4le)."""
    try:
        return f"{float(value):.3f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def _date(value, fallback="—"):
    if value is None:
        return fallback
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(value)


def _p(text, style):
    return Paragraph(escape(_text(text)), style)


# ── En-tête / pied de page ────────────────────────────────────────────────────

def _page_callback(canvas, doc):
    canvas.saveState()
    page_width, page_height = doc.pagesize
    if LOGO_PATH.exists():
        canvas.drawImage(
            ImageReader(str(LOGO_PATH)),
            doc.leftMargin, page_height - 19 * mm,
            width=31 * mm, height=13.3 * mm,
            preserveAspectRatio=True, mask="auto",
        )
    canvas.setStrokeColor(OLEA_TERRACOTTA)
    canvas.setLineWidth(1.2)
    canvas.line(
        doc.leftMargin, page_height - 21 * mm,
        page_width - doc.rightMargin, page_height - 21 * mm,
    )
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(TEXT)
    canvas.drawRightString(
        page_width - doc.rightMargin, page_height - 13 * mm,
        "REPORTING TRÉSORERIE",
    )
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 7 * mm, "Document généré par OLEA Finance")
    canvas.drawRightString(page_width - doc.rightMargin, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


# ── KPI summary table ─────────────────────────────────────────────────────────

def _build_kpi_table(totaux: dict, styles: dict):
    """
    Présentation en 6 cartes / cellules KPI en ligne (comme sur l'écran et la balance âgée),
    au lieu de tables imbriquées superposées.
    Total utile en paysage A4 : ~268 mm (6 x 44.6 mm).
    """
    exp_net = totaux.get("tresorerie_nette_exploitation") or 0
    hors_net = totaux.get("tresorerie_nette_hors_exploitation") or 0

    kpis = [
        {
            "label": "Recette exploitation",
            "val": totaux.get("recette_exploitation"),
            "sub": "Exploitation + comm.",
            "color": OLEA_TERRACOTTA,
            "neg": False,
        },
        {
            "label": "Dépense exploitation",
            "val": totaux.get("depense_exploitation"),
            "sub": "Exploitation + comm.",
            "color": OLEA_TERRACOTTA,
            "neg": False,
        },
        {
            "label": "Tréso. nette expl.",
            "val": exp_net,
            "sub": "Recette − dépense",
            "color": OLEA_TERRACOTTA,
            "neg": exp_net < 0,
        },
        {
            "label": "Recette hors expl.",
            "val": totaux.get("recette_hors_exploitation"),
            "sub": "Toutes banques",
            "color": OLEA_AMBER,
            "neg": False,
        },
        {
            "label": "Dépense hors expl.",
            "val": totaux.get("depense_hors_exploitation"),
            "sub": "Toutes banques",
            "color": OLEA_AMBER,
            "neg": False,
        },
        {
            "label": "Tréso. nette hors",
            "val": hors_net,
            "sub": "Recette − dépense",
            "color": OLEA_AMBER,
            "neg": hors_net < 0,
        },
    ]

    header_cells = []
    value_cells = []
    sub_cells = []

    for item in kpis:
        val_color = OLEA_TERRACOTTA if item["neg"] else TEXT
        
        lbl_style = ParagraphStyle(
            "KpiH_" + item["label"][:4], parent=styles["base"],
            fontName="Helvetica-Bold", fontSize=7, leading=9,
            textColor=MUTED, alignment=TA_CENTER,
        )
        val_style = ParagraphStyle(
            "KpiV_" + item["label"][:4], parent=styles["base"],
            fontName="Helvetica-Bold", fontSize=10, leading=12,
            textColor=val_color, alignment=TA_CENTER,
        )
        sub_style = ParagraphStyle(
            "KpiS_" + item["label"][:4], parent=styles["base"],
            fontName="Helvetica", fontSize=6, leading=8,
            textColor=MUTED, alignment=TA_CENTER,
        )

        header_cells.append(Paragraph(escape(item["label"]), lbl_style))
        value_cells.append(Paragraph(escape(_money(item["val"])), val_style))
        sub_cells.append(Paragraph(escape(item["sub"]), sub_style))

    # Largeur colonne : 268 mm / 6 = 44.66 mm
    col_w = [44.66 * mm] * 6
    kpi_table = Table([header_cells, value_cells, sub_cells], colWidths=col_w, hAlign="LEFT")

    t_styles = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 1),
        ("TOPPADDING", (0, 2), (-1, 2), 1),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 4),
    ]

    # Bordures supérieures colorées pour chaque KPI card (effet KPI dashboard OLEA)
    for i, item in enumerate(kpis):
        t_styles.append(("LINEABOVE", (i, 0), (i, 0), 2.0, item["color"]))

    kpi_table.setStyle(TableStyle(t_styles))
    return kpi_table


# ── Tableau principal par banque ───────────────────────────────────────────────

def _build_detail_table(banques: list, totaux: dict, styles: dict):
    """Tableau complet des ratios par banque (paysage A4)."""
    hdr = styles["table_header"]
    cell = styles["table_cell"]
    num = styles["num_cell"]
    num_neg = styles["num_neg"]
    tot = styles["total_cell"]

    # Largeurs colonnes (total ≈ 270 mm)
    # Banque | Rec.Exp | Comm.R | Dep.Exp | Comm.D | Net.Exp || Rec.Hors | Dep.Hors | Net.Hors || S.Dep | Solde | NC
    COL_W = [32*mm, 22*mm, 18*mm, 22*mm, 18*mm, 22*mm, 20*mm, 20*mm, 20*mm, 22*mm, 22*mm, 18*mm]

    def row(b, style_num=num, style_tot=None):
        s = style_tot or style_num
        net_exp = b.get("tresorerie_nette_exploitation")
        net_hors = b.get("tresorerie_nette_hors_exploitation")
        solde = b.get("solde")
        # Couleur négative pour les nets
        s_net_exp = num_neg if (net_exp is not None and net_exp < 0) else s
        s_net_hors = num_neg if (net_hors is not None and net_hors < 0) else s
        s_solde = num_neg if (solde is not None and solde < 0) else s
        nc = b.get("non_classe_count", 0)
        return [
            # Toujours `cell` (aligné à gauche) : le TableStyle ne peut pas
            # corriger l'alignement interne d'un Paragraph.
            _p(b.get("compte_banque", "?"), cell),
            Paragraph(escape(_money(b.get("recette_exploitation"))), s),
            Paragraph(escape(_money(b.get("dont_recette_commission"))), s),
            Paragraph(escape(_money(b.get("depense_exploitation"))), s),
            Paragraph(escape(_money(b.get("dont_depense_commission"))), s),
            Paragraph(escape(_money(b.get("tresorerie_nette_exploitation"))), s_net_exp),
            Paragraph(escape(_money(b.get("recette_hors_exploitation"))), s),
            Paragraph(escape(_money(b.get("depense_hors_exploitation"))), s),
            Paragraph(escape(_money(b.get("tresorerie_nette_hors_exploitation"))), s_net_hors),
            Paragraph(escape(_money(b.get("solde_ouverture"))), s),
            Paragraph(escape(_money(solde)), s_solde),
            Paragraph(escape(str(nc) if nc else "—"), s),
        ]

    # Sous-en-têtes (2 lignes)
    headers = [
        [
            Paragraph("Banque", hdr),
            Paragraph("Exploitation (commissions incluses)", hdr), "", "", "", "",
            Paragraph("Hors exploitation", hdr), "", "",
            Paragraph("Solde du compte", hdr), "",
            Paragraph("NC", hdr),
        ],
        [
            "",
            Paragraph("Recette", hdr),
            Paragraph("dont comm.", hdr),
            Paragraph("Dépense", hdr),
            Paragraph("dont comm.", hdr),
            Paragraph("Tréso. nette", hdr),
            Paragraph("Recette", hdr),
            Paragraph("Dépense", hdr),
            Paragraph("Tréso. nette", hdr),
            Paragraph("Solde départ", hdr),
            Paragraph("Solde", hdr),
            Paragraph("Non classés", hdr),
        ],
    ]

    body = [row(b) for b in banques]
    # Libellé lisible pour la ligne de total (les polices standard n'ont pas
    # de glyphe pour « ⚠ »/« ✓ » : on garde du texte pur, imprimable partout).
    libelle_totaux = {**totaux, "compte_banque": "Total toutes banques"}
    total_row = row(libelle_totaux, style_tot=tot)

    table = Table(
        [*headers, *body, total_row],
        colWidths=COL_W,
        repeatRows=2,
        hAlign="LEFT",
    )

    # Nombre de lignes de données (sans les 2 lignes d'en-tête)
    nb_data = len(body)
    # Index de la ligne total (après les 2 en-têtes + nb_data lignes de données)
    total_idx = 2 + nb_data

    table.setStyle(TableStyle([
        # Fusion des en-têtes de groupe (ligne 0)
        ("SPAN", (1, 0), (5, 0)),   # Exploitation
        ("SPAN", (6, 0), (8, 0)),   # Hors exploitation
        ("SPAN", (9, 0), (10, 0)),  # Solde du compte
        # Arrière-plans des groupes alignés sur la charte du logo OLEA
        ("BACKGROUND", (0, 0), (0, 1), OLEA_TERRACOTTA),
        ("BACKGROUND", (1, 0), (5, 1), OLEA_TERRACOTTA),       # Bloc Exploitation : Terracotta
        ("BACKGROUND", (6, 0), (8, 1), OLEA_AMBER),            # Bloc Hors-exploitation : Ambre / Ocre
        ("BACKGROUND", (9, 0), (10, 1), OLEA_TERRACOTTA_DARK),  # Bloc Solde : Terracotta foncé
        ("BACKGROUND", (11, 0), (11, 1), OLEA_ANTHRACITE),      # Bloc Non classés : Anthracite
        # Couleur texte entêtes
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        # Lignes séparatrices verticales entre groupes
        ("LINEBEFORE", (1, 0), (1, -1), 1.0, colors.white),
        ("LINEBEFORE", (6, 0), (6, -1), 1.2, colors.HexColor("#C47816")),
        ("LINEBEFORE", (9, 0), (9, -1), 1.2, colors.white),
        ("LINEBEFORE", (11, 0), (11, -1), 1.0, colors.white),
        # Grille générale
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("LINEABOVE", (0, 0), (-1, 0), 1.5, OLEA_TERRACOTTA),
        # Alignement numérique
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        # Alternance lignes de données
        ("ROWBACKGROUNDS", (0, 2), (-1, total_idx - 1), [colors.white, ROW_ALT]),
        # Ligne totaux
        ("BACKGROUND", (0, total_idx), (-1, total_idx), ROW_TOTAL),
        ("LINEABOVE", (0, total_idx), (-1, total_idx), 1.2, OLEA_TERRACOTTA),
        # Paddings
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


# ── Point d'entrée public ─────────────────────────────────────────────────────

def build_tresorerie_pdf(
    banques: list,
    totaux: dict,
    controle: dict,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
) -> BytesIO:
    """
    Génère le PDF du reporting trésorerie et renvoie un BytesIO prêt à streamer.

    Args:
        banques  : liste de dicts renvoyés par construire_reporting()
        totaux   : dict renvoyé par totaliser()
        controle : dict statut / non_classes / écarts
        date_debut / date_fin : filtres de période appliqués (optionnels)
    """
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=27 * mm,
        bottomMargin=13 * mm,
        title="Reporting Trésorerie OLEA",
        author="OLEA",
    )

    base = getSampleStyleSheet()
    styles: dict = {
        "base": ParagraphStyle(
            "Base", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, leading=10, textColor=TEXT,
        ),
        "title": ParagraphStyle(
            "PdfTitle", parent=base["Title"],
            fontName="Helvetica-Bold", fontSize=18, leading=22,
            textColor=TEXT, alignment=TA_LEFT, spaceAfter=3 * mm,
        ),
        "document_ref": ParagraphStyle(
            "PdfDocumentRef", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7, leading=9,
            textColor=OLEA_TERRACOTTA,
        ),
        "section": ParagraphStyle(
            "PdfSection", parent=base["Heading2"],
            fontName="Helvetica-Bold", fontSize=10.5, leading=14,
            textColor=OLEA_TERRACOTTA,
            spaceBefore=4 * mm, spaceAfter=2 * mm,
        ),
        "table_header": ParagraphStyle(
            "PdfTableHeader", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=6.3, leading=7.5,
            textColor=colors.white, alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "PdfTableCell", parent=base["Normal"],
            fontName="Helvetica", fontSize=6.5, leading=7.8, textColor=TEXT,
        ),
        "num_cell": ParagraphStyle(
            "PdfNumCell", parent=base["Normal"],
            fontName="Helvetica", fontSize=6.5, leading=7.8,
            textColor=TEXT, alignment=TA_RIGHT,
        ),
        "num_neg": ParagraphStyle(
            "PdfNumNeg", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=6.5, leading=7.8,
            textColor=OLEA_TERRACOTTA, alignment=TA_RIGHT,
        ),
        "total_cell": ParagraphStyle(
            "PdfTotalCell", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7, leading=9,
            textColor=TEXT, alignment=TA_RIGHT,
        ),
        "note": ParagraphStyle(
            "PdfNote", parent=base["Normal"],
            fontName="Helvetica-Oblique", fontSize=7, leading=9,
            textColor=MUTED, spaceAfter=2 * mm,
        ),
        "note_ok": ParagraphStyle(
            "PdfNoteOk", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8, leading=10,
            textColor=colors.HexColor("#25714A"), leftIndent=2 * mm,
        ),
        "note_warn": ParagraphStyle(
            "PdfNoteWarn", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8, leading=10,
            textColor=OLEA_TERRACOTTA, leftIndent=2 * mm,
        ),
        "context_label": ParagraphStyle(
            "PdfContextLabel", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=MUTED,
        ),
        "context_value": ParagraphStyle(
            "PdfContextValue", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=TEXT,
        ),
        "empty": ParagraphStyle(
            "PdfEmpty", parent=base["Normal"],
            fontName="Helvetica-Oblique", fontSize=8, leading=10,
            textColor=MUTED, leftIndent=3 * mm,
        ),
    }

    generated_at = datetime.now().strftime("%d/%m/%Y à %H:%M")

    # ── Période formatée ──
    if date_debut and date_fin:
        periode_txt = f"Du {_date(date_debut)} au {_date(date_fin)}"
    elif date_debut:
        periode_txt = f"À partir du {_date(date_debut)}"
    elif date_fin:
        periode_txt = f"Jusqu'au {_date(date_fin)}"
    else:
        periode_txt = "Toutes périodes"

    # ── Bloc contexte (entête informatif) ──
    context_data = [
        [
            Paragraph("Période analysée", styles["context_label"]),
            Paragraph("Nombre de banques", styles["context_label"]),
            Paragraph("Statut du reporting", styles["context_label"]),
            Paragraph("Date d'édition", styles["context_label"]),
        ],
        [
            Paragraph(escape(periode_txt), styles["context_value"]),
            Paragraph(escape(str(len(banques))), styles["context_value"]),
            Paragraph(escape(controle.get("statut", "—")), styles["context_value"]),
            Paragraph(escape(generated_at), styles["context_value"]),
        ],
    ]
    context_table = Table(context_data, colWidths=[67 * mm] * 4)
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

    # ── Story ──
    story = [
        Paragraph("Reporting Trésorerie", styles["title"]),
        Paragraph(
            f"RAPPORT DE TRÉSORERIE · ÉDITÉ LE {generated_at.upper()}",
            styles["document_ref"],
        ),
        Spacer(1, 3 * mm),
        context_table,
        Spacer(1, 4 * mm),
    ]

    # ── KPIs ──
    story.append(Paragraph("Synthèse globale", styles["section"]))
    story.append(_build_kpi_table(totaux, styles))
    story.append(Spacer(1, 4 * mm))

    # ── Tableau détaillé ──
    if banques:
        story.append(Paragraph("Ratios par banque", styles["section"]))
        story.append(_build_detail_table(banques, totaux, styles))
        story.append(Spacer(1, 3 * mm))
    else:
        story.append(Paragraph("Aucune donnée disponible pour la période sélectionnée.", styles["empty"]))
        story.append(Spacer(1, 3 * mm))

    # ── Note de bas de tableau ──
    story.append(Paragraph(
        "Recette exploitation = crédits d'exploitation + commissions · "
        "Dépense exploitation = débits d'exploitation + commissions · "
        "Trésorerie nette = recette − dépense · "
        "NC = mouvements non classés (exclus des ratios)",
        styles["note"],
    ))

    # ── Statut du contrôle de cohérence ──
    statut = controle.get("statut", "")
    if statut == "OK":
        story.append(Paragraph("Reporting complet — tous les mouvements sont classés.", styles["note_ok"]))
    elif statut == "INCOMPLET":
        nc = controle.get("non_classes", 0)
        story.append(Paragraph(
            f"Attention : {nc} mouvement(s) non classé(s) n'entrent dans aucun ratio.",
            styles["note_warn"],
        ))
    elif statut == "ERREUR":
        ed = controle.get("ecart_debit", 0)
        ec = controle.get("ecart_credit", 0)
        story.append(Paragraph(
            f"Attention : contrôle de cohérence en échec — écart débit {_decimal(ed)}, "
            f"écart crédit {_decimal(ec)}.",
            styles["note_warn"],
        ))

    document.build(story, onFirstPage=_page_callback, onLaterPages=_page_callback)
    buffer.seek(0)
    return buffer

