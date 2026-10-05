"""Export PDF et impression de la balance âgée (clients / fournisseurs).

Même charte que les exports Reporting et Rapprochement bancaire : A4 paysage, logo OLEA, filet terracotta,
cartes d'information, tableaux à en-tête terracotta, pied de page « Document généré par OLEA Finance ».
Les deux balances alimentent le même moteur via un « rapport » normalisé (dict) : voir rapport_clients()
et rapport_fournisseurs().
"""
import base64
import html
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import CondPageBreak, KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PRIMARY = colors.HexColor("#B4482B")
PRIMARY_LIGHT = colors.HexColor("#F8ECE8")
AMBER_LIGHT = colors.HexColor("#FFF3DD")
TEXT = colors.HexColor("#30343A")
MUTED = colors.HexColor("#667085")
GRID = colors.HexColor("#E1E3E5")
SUB = colors.HexColor("#F8F8F7")
CHARGE = colors.HexColor("#FCEBE6")
META_LINE = colors.HexColor("#E5C9C0")
LOGO_PATH = Path(__file__).resolve().parents[1] / "rapprochement_bancaire" / "olea-logo.png"   # logo partagé

BUCKET_KEYS = ["non_echu", "1-30", "31-60", "61-90", "+90"]
BUCKET_LABELS = ["Non échu", "1-30 j", "31-60 j", "61-90 j", "+90 j"]
NBSP = "\u00a0"
WIDTH = 277 * mm        # largeur utile (A4 paysage – marges 10 mm)


# ───────────────────────── Formats ─────────────────────────
def _m(v, plus: bool = False) -> str:
    v = float(v or 0)
    if abs(v) < 0.0005:
        return "0,000"
    s = f"{abs(v):,.3f}".replace(",", NBSP).replace(".", ",")
    return ("-" if v < 0 else "+" if plus else "") + s


def _z(v) -> str:
    return "-" if abs(float(v or 0)) < 0.0005 else _m(v)


def _d(iso: str) -> str:
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(iso or "-")


def _safe(v) -> str:
    """Helvetica (WinAnsi) : on remplace les caractères hors jeu pour éviter les carrés noirs."""
    return str(v if v is not None else "").encode("cp1252", "replace").decode("cp1252")


def _esc(v) -> str:
    return html.escape(_safe(v))


def _pct(v, total) -> str:
    return f"{(v / total * 100):.0f} %" if total and total > 0 else "0 %"


def _short(v: Optional[str], n: int = 42) -> str:
    v = v or "-"
    return v if len(v) <= n else v[: n - 1] + "…"


# ───────────────────────── Rapport normalisé ─────────────────────────
def _b5(t) -> List[float]:
    return [t.non_echu, t.echu_30, t.echu_60, t.echu_90, t.echu_plus]


def _b5_contre(t) -> List[float]:
    av = t.avance_buckets or {}
    return [av.get(k, 0.0) for k in BUCKET_KEYS]


def _ecritures(tiers: List[Any], natures: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    for t in tiers:
        rows = []
        for l in t.lignes:
            if l.reste_du > 0.0005 and l.sens in natures:
                lab = BUCKET_LABELS[BUCKET_KEYS.index(l.bucket)] if l.bucket in BUCKET_KEYS else "-"
                rows.append([l.date, l.libelle, natures[l.sens], l.debit, l.credit, l.reste_du, max(l.jours_retard, 0), lab])
        if rows:
            out.append({"nom": t.nom, "code": t.code, "rows": rows})
    return out


def rapport_clients(d, fichier: Optional[str] = None, detail: bool = True) -> Dict[str, Any]:
    deb = [c for c in d.clients if c.total_solde > 0]
    cre = sorted([c for c in d.clients if c.total_solde < 0], key=lambda c: c.total_solde)
    tot_echu = sum(d.totaux_buckets.get(k, 0.0) for k in BUCKET_KEYS[1:])
    return {
        "titre": "Balance âgée clients", "entete": "BALANCE ÂGÉE CLIENTS", "tiers": "Client", "tiers_pl": "clients",
        "date_reference": d.date_reference, "fichier": fichier, "nb": d.nb_clients,
        "kpis": [
            ("Créances clients", d.total_debiteur, f"{len(deb)} client(s) débiteur(s)"),
            ("Dont échu", tot_echu, f"{_pct(tot_echu, d.total_debiteur)} des créances"),
            ("Avances / avoirs", d.total_crediteur, f"{len(cre)} client(s) créditeur(s)"),
            ("Solde net Sage", d.total_general, "Créances - avances"),
        ],
        "aging": {"titre": "Ancienneté des créances", "total": d.total_debiteur, "buckets": d.totaux_buckets},
        "aging_contre": {"titre": "Ancienneté des avances / avoirs (depuis l'encaissement)",
                         "total": -d.total_crediteur, "buckets": d.totaux_avances},
        "principal": {"titre": "Détail des créances par client", "extra": [],
                      "rows": [{"nom": c.nom, "code": c.code, "solde": c.total_solde, "b": _b5(c), "x": []} for c in deb]},
        "contre": {"titre": "Clients créditeurs : avances / avoirs non imputés", "extra": [],
                   "rows": [{"nom": c.nom, "code": c.code, "solde": c.total_solde, "b": _b5_contre(c), "x": []} for c in cre]},
        "autres": None,
        "ecritures": _ecritures(deb + cre, {"D": "Créance", "C": "Avance"}) if detail else [],
    }


def rapport_fournisseurs(d, fichier: Optional[str] = None, detail: bool = True) -> Dict[str, Any]:
    deb = [f for f in d.fournisseurs if f.total_solde > 0]
    cre = sorted([f for f in d.fournisseurs if f.total_solde < 0], key=lambda f: f.total_solde)
    zero = [f for f in d.fournisseurs if f.total_solde == 0 and (abs(f.fnp) > 0.0005 or abs(f.avance_409) > 0.0005)]
    p90 = d.totaux_buckets.get("+90", 0.0)

    def ligne(f, bucket_fn):
        return {"nom": f.nom, "code": f.code, "solde": f.total_solde, "b": bucket_fn(f), "x": [f.fnp, f.avance_409]}

    return {
        "titre": "Balance âgée fournisseurs", "entete": "BALANCE ÂGÉE FOURNISSEURS", "tiers": "Fournisseur",
        "tiers_pl": "fournisseurs", "date_reference": d.date_reference, "fichier": fichier, "nb": d.nb_fournisseurs,
        "kpis": [
            ("Dettes fournisseurs (401)", d.total_dettes, f"{len(deb)} fournisseur(s)"),
            ("Dont > 90 jours", p90, f"{_pct(p90, d.total_dettes)} des dettes"),
            ("Paiements non imputés", d.total_non_imputes, f"{len(cre)} fournisseur(s) nous doivent"),
            ("Factures non parvenues (408)", d.total_fnp, "À recevoir, hors balance âgée"),
            ("Avances versées (409)", d.total_avances, "Acomptes à imputer sur factures"),
            ("Net tous comptes", d.total_net, "401 + 408 - 409"),
        ],
        "aging": {"titre": "Ancienneté des dettes", "total": d.total_dettes, "buckets": d.totaux_buckets},
        "aging_contre": {"titre": "Ancienneté des paiements non imputés (depuis le paiement)",
                         "total": -d.total_non_imputes, "buckets": d.totaux_avances},
        "principal": {"titre": "Détail des dettes par fournisseur", "extra": ["FNP (408)", "Avances (409)"],
                      "rows": [ligne(f, _b5) for f in deb]},
        "contre": {"titre": "Fournisseurs débiteurs : paiements non imputés", "extra": ["FNP (408)", "Avances (409)"],
                   "rows": [ligne(f, _b5_contre) for f in cre]},
        "autres": {"titre": "Autres comptes : factures non parvenues (408) et avances versées (409)",
                   "rows": [{"nom": f.nom, "code": f.code, "x": [f.fnp, f.avance_409]} for f in zero]} if zero else None,
        "ecritures": _ecritures(deb + cre, {"D": "Dette", "C": "Non imputé"}) if detail else [],
    }


# ───────────────────────── PDF (ReportLab) ─────────────────────────
def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "title": ParagraphStyle("BalTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22,
                                alignment=TA_LEFT, textColor=TEXT, spaceAfter=4 * mm),
        "section": ParagraphStyle("BalSection", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11,
                                  leading=14, textColor=PRIMARY, spaceBefore=2 * mm, spaceAfter=3 * mm, keepWithNext=1),
        "note": ps("BalNote", fontName="Helvetica-Oblique", fontSize=7.2, leading=9.5, textColor=MUTED, spaceAfter=1.5 * mm),
        "meta_label": ps("BalMetaLabel", fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=MUTED),
        "meta_value": ps("BalMetaValue", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=TEXT),
        "head": ps("BalHead", fontName="Helvetica-Bold", fontSize=6.8, leading=8.2, textColor=colors.white),
        "head_r": ps("BalHeadR", fontName="Helvetica-Bold", fontSize=6.8, leading=8.2, textColor=colors.white, alignment=TA_RIGHT),
        "cell": ps("BalCell", fontName="Helvetica", fontSize=6.8, leading=8.2, textColor=TEXT),
        "cell_r": ps("BalCellR", fontName="Helvetica", fontSize=6.8, leading=8.2, textColor=TEXT, alignment=TA_RIGHT),
        "cell_b": ps("BalCellB", fontName="Helvetica-Bold", fontSize=6.8, leading=8.2, textColor=TEXT),
        "cell_br": ps("BalCellBR", fontName="Helvetica-Bold", fontSize=6.8, leading=8.2, textColor=TEXT, alignment=TA_RIGHT),
    }


def _p(v, style) -> Paragraph:
    return Paragraph(_esc(v), style)


def _nom(nom, code, st) -> Paragraph:
    return Paragraph(f'<b>{_esc(nom)}</b><br/><font size="5.8" color="#667085">{_esc(code)}</font>', st["cell"])


def _grid(headers, rows, widths, st, num_from=1, total=None, hot=(), long=False, spans=(), num_to=99):
    """rows : listes de str ou Paragraph. total : ligne de total. hot : cellules (ligne, col) à surligner.
    spans / band : lignes d'intertitre (index dans rows) fusionnées sur toute la largeur."""
    isnum = lambda i: num_from <= i < num_to
    data = [[_p(h, st["head_r"] if isnum(i) else st["head"]) for i, h in enumerate(headers)]]
    for r in rows:
        data.append([c if isinstance(c, Paragraph) else _p(c, st["cell_r"] if isnum(i) else st["cell"])
                     for i, c in enumerate(r)])
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("GRID", (0, 0), (-1, -1), 0.3, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SUB]),
    ]
    for ri, ci in hot:
        cmds.append(("BACKGROUND", (ci, ri + 1), (ci, ri + 1), CHARGE))
    for ri in spans:
        cmds += [("SPAN", (0, ri + 1), (-1, ri + 1)), ("BACKGROUND", (0, ri + 1), (-1, ri + 1), AMBER_LIGHT)]
    if total:
        data.append([_p(v, st["cell_br"] if isnum(i) else st["cell_b"]) for i, v in enumerate(total)])
        n = len(data) - 1
        cmds += [("BACKGROUND", (0, n), (-1, n), PRIMARY_LIGHT), ("LINEABOVE", (0, n), (-1, n), 0.9, PRIMARY)]
    t = (LongTable if long else Table)(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle(cmds))
    return t


def _aging_block(a: Dict[str, Any], st) -> List[Any]:
    total = a["total"] or 0.0
    rows = [[lab, _m(a["buckets"].get(k, 0.0)), _pct(a["buckets"].get(k, 0.0), total)] for k, lab in zip(BUCKET_KEYS, BUCKET_LABELS)]
    out: List[Any] = [Paragraph(_esc(a["titre"]), st["section"])]
    out += [_grid(["Tranche", "Montant (TND)", "% du total"], rows, [60 * mm, 55 * mm, 30 * mm], st,
                  total=["Total", _m(total), "100 %" if total > 0 else "0 %"]), Spacer(1, 4 * mm)]
    return [KeepTogether(out)]


def _decor(entete: str):
    def draw(canvas, doc):
        w, h = landscape(A4)
        canvas.saveState()
        if LOGO_PATH.is_file():
            canvas.drawImage(ImageReader(str(LOGO_PATH)), doc.leftMargin, h - 19 * mm, width=31 * mm, height=13.3 * mm,
                             preserveAspectRatio=True, mask="auto")
        else:
            canvas.setFont("Helvetica-Bold", 15)
            canvas.setFillColor(PRIMARY)
            canvas.drawString(doc.leftMargin, h - 13 * mm, "OLEA")
        canvas.setStrokeColor(PRIMARY)
        canvas.setLineWidth(1.2)
        canvas.line(doc.leftMargin, h - 21 * mm, w - doc.rightMargin, h - 21 * mm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(TEXT)
        canvas.drawRightString(w - doc.rightMargin, h - 13 * mm, entete)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 7 * mm, "Document généré par OLEA Finance")
        canvas.drawRightString(w - doc.rightMargin, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def _tiers_table(blk: Dict[str, Any], tiers_label: str, st) -> List[Any]:
    rows, extra = blk["rows"], blk["extra"]
    heads = [tiers_label, "Solde", *BUCKET_LABELS, *extra]
    n_num = len(heads) - 1
    wn = (WIDTH - 62 * mm) / n_num
    body, hot = [], []
    sums = [0.0] * n_num
    for ri, r in enumerate(rows):
        vals = [r["solde"], *r["b"], *r["x"]]
        body.append([_nom(r["nom"], r["code"], st), _m(vals[0]), *[_z(v) for v in vals[1:]]])
        for i, v in enumerate(vals):
            sums[i] += v
        if r["b"][4] > 0.0005:
            hot.append((ri, 6))                     # +90 j surligné
    return [Paragraph(_esc(f"{blk['titre']} ({len(rows)})"), st["section"]),
            _grid(heads, body, [62 * mm] + [wn] * n_num, st, total=["Total", *[_m(s) for s in sums]], hot=hot, long=True),
            Spacer(1, 5 * mm)]


def build_pdf(r: Dict[str, Any]) -> BytesIO:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=27 * mm,
                            bottomMargin=13 * mm, title=f"{r['titre']} au {_d(r['date_reference'])}", author="OLEA")
    st = _styles()
    generated = datetime.now().strftime("%d/%m/%Y à %H:%M")

    meta = Table([
        [_p("SITUATION AU", st["meta_label"]), _p("SOURCE", st["meta_label"]), _p("DATE D'ÉDITION", st["meta_label"]),
         _p(r["tiers_pl"].upper(), st["meta_label"])],
        [_p(_d(r["date_reference"]), st["meta_value"]), _p(_short(r["fichier"]), st["meta_value"]),
         _p(generated, st["meta_value"]), _p(r["nb"], st["meta_value"])],
    ], colWidths=[45 * mm, 110 * mm, 62 * mm, 45 * mm], hAlign="LEFT")
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_LIGHT), ("LINEABOVE", (0, 0), (-1, 0), 2, PRIMARY),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, META_LINE), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]))

    kpi_rows = [[k, _m(v), c] for k, v, c in r["kpis"]]
    story: List[Any] = [Paragraph(_esc(r["titre"]), st["title"]), meta, Spacer(1, 6 * mm),
                        Paragraph("Synthèse", st["section"]),
                        _grid(["Indicateur", "Montant (TND)", "Détail"], kpi_rows, [90 * mm, 60 * mm, 110 * mm], st, num_from=1, num_to=2),
                        Spacer(1, 5 * mm)]
    story += _aging_block(r["aging"], st)
    if r["aging_contre"]["total"] > 0.0005:
        story += _aging_block(r["aging_contre"], st)

    story.append(CondPageBreak(75 * mm))
    if r["principal"]["rows"]:
        story += _tiers_table(r["principal"], r["tiers"], st)
    else:
        story += [Paragraph(_esc(r["principal"]["titre"]), st["section"]), Paragraph("Aucune donnée dans cette catégorie.", st["note"])]
    if r["contre"]["rows"]:
        story += _tiers_table(r["contre"], r["tiers"], st)
    if r["autres"]:
        rows = [[_nom(x["nom"], x["code"], st), _z(x["x"][0]), _z(x["x"][1])] for x in r["autres"]["rows"]]
        story += [Paragraph(_esc(f"{r['autres']['titre']} ({len(rows)})"), st["section"]),
                  _grid([r["tiers"], "FNP (408)", "Avances (409)"], rows, [120 * mm, 55 * mm, 55 * mm], st, long=True), Spacer(1, 5 * mm)]

    if r["ecritures"]:
        rows, spans = [], []
        for g in r["ecritures"]:
            spans.append(len(rows))
            rows.append([Paragraph(f'<b>{_esc(g["nom"])}</b> &nbsp;<font color="#667085">{_esc(g["code"])}</font>', st["cell"])] + [""] * 7)
            for d_, lib, nat, deb, cre, reste, jours, lab in g["rows"]:
                rows.append([d_, _p(lib, st["cell"]), nat, _z(deb), _z(cre), _m(reste), f"{jours} j", lab])
        story += [PageBreak(), Paragraph(_esc(f"Écritures ouvertes par {r['tiers'].lower()}"), st["section"]),
                  Paragraph("Écritures non soldées après imputation des règlements sur les pièces les plus anciennes (FIFO).", st["note"]),
                  _grid(["Date", "Libellé", "Nature", "Débit", "Crédit", "Reste", "Ancienneté", "Tranche"], rows,
                        [17 * mm, 106 * mm, 22 * mm, 27 * mm, 27 * mm, 30 * mm, 22 * mm, 26 * mm], st, num_from=3, num_to=7, long=True, spans=spans),
                  Spacer(1, 5 * mm)]

    deco = _decor(r["entete"])
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    buf.seek(0)
    return buf


# ───────────────────────── Impression (HTML, ouvert dans le navigateur) ─────────────────────────
def _logo_data_uri() -> str:
    if not LOGO_PATH.is_file():
        return ""
    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


_CSS = """
@page { size: A4 landscape; margin: 12mm; }
* { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
body { margin: 0; font-family: Arial, sans-serif; color: #30343a; background: #fff; }
.sheet { position: relative; min-height: 178mm; page-break-after: always; padding-bottom: 8mm; }
.sheet:last-child { page-break-after: auto; }
table { border-collapse: collapse; width: 100%; font-size: 10.5px; }
.print-header { border-bottom: 2px solid #b4482b; margin-bottom: 14px; }
.print-header td { padding: 0 0 7px; border: 0; }
.print-header .r { text-align: right; color: #30343a; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; }
.logo { display: block; width: 96px; height: auto; max-height: 44px; }
.eyebrow { color: #b4482b; font-size: 9px; font-weight: 700; letter-spacing: 1.15px; margin-bottom: 3px; }
h1 { margin: 0 0 12px; color: #30343a; font-size: 22px; line-height: 1.2; }
h2 { margin: 14px 0 9px; color: #b4482b; font-size: 15px; }
.note { color: #667085; font-size: 9px; font-style: italic; margin: -4px 0 8px; }
.meta { width: auto; background: #f8ece8; border-top: 3px solid #b4482b; margin-bottom: 14px; }
.meta td { padding: 7px 14px; border: 0; border-left: 1px solid #e5c9c0; vertical-align: top; }
.meta td:first-child { border-left: 0; }
.meta small { display: block; color: #667085; font-size: 8px; font-weight: 700; letter-spacing: .55px; }
.meta strong { display: block; margin-top: 2px; font-size: 10px; }
.data th { background: #b4482b; color: #fff; border: 1px solid #b4482b; padding: 6px; text-align: left; font-size: 9px; }
.data td { border: 1px solid #e1e3e5; padding: 5px 6px; }
.data tbody tr:nth-child(even) td { background: #fbfbfa; }
.data thead { display: table-header-group; }
.data tr { page-break-inside: avoid; }
.num { text-align: right !important; white-space: nowrap; }
.code { color: #667085; font-size: 8px; }
.hot { background: #fcebe6 !important; font-weight: 700; }
.tot td { background: #f8ece8 !important; font-weight: 700; border-top: 2px solid #b4482b; }
.band td { background: #fff3dd !important; font-weight: 700; }
footer { position: absolute; bottom: 0; left: 0; right: 0; border-top: 1px solid #e1e3e5; padding-top: 5px; color: #667085; font-size: 8px; }
"""


def _h_table(headers, rows, num_from=1, total=None, hot=(), bands=(), num_to=99) -> str:
    isnum = lambda i: num_from <= i < num_to
    th = "".join(f'<th class="{"num" if isnum(i) else ""}">{_esc(h)}</th>' for i, h in enumerate(headers))
    out = []
    for ri, r in enumerate(rows):
        if ri in bands:
            out.append(f'<tr class="band"><td colspan="{len(headers)}">{r[0]}</td></tr>')
            continue
        tds = "".join(
            f'<td class="{"num" if isnum(i) else ""}{" hot" if (ri, i) in hot else ""}">{c}</td>' for i, c in enumerate(r))
        out.append(f"<tr>{tds}</tr>")
    if total:
        out.append('<tr class="tot">' + "".join(f'<td class="{"num" if isnum(i) else ""}">{_esc(v)}</td>' for i, v in enumerate(total)) + "</tr>")
    return f'<table class="data"><thead><tr>{th}</tr></thead><tbody>{"".join(out)}</tbody></table>'


def _h_aging(a) -> str:
    total = a["total"] or 0.0
    rows = [[_esc(lab), _m(a["buckets"].get(k, 0.0)), _pct(a["buckets"].get(k, 0.0), total)] for k, lab in zip(BUCKET_KEYS, BUCKET_LABELS)]
    return (f"<h2>{_esc(a['titre'])}</h2>"
            + '<div style="width:150mm">' + _h_table(["Tranche", "Montant (TND)", "% du total"], rows, total=["Total", _m(total), "100 %" if total > 0 else "0 %"]) + "</div>")


def _h_tiers(blk, label) -> str:
    rows, extra = blk["rows"], blk["extra"]
    heads = [label, "Solde", *BUCKET_LABELS, *extra]
    body, hot, sums = [], [], [0.0] * (len(heads) - 1)
    for ri, r in enumerate(rows):
        vals = [r["solde"], *r["b"], *r["x"]]
        body.append([f'<b>{_esc(r["nom"])}</b><div class="code">{_esc(r["code"])}</div>', _m(vals[0]), *[_z(v) for v in vals[1:]]])
        for i, v in enumerate(vals):
            sums[i] += v
        if r["b"][4] > 0.0005:
            hot.append((ri, 6))
    return f"<h2>{_esc(blk['titre'])} ({len(rows)})</h2>" + _h_table(heads, body, total=["Total", *[_m(s) for s in sums]], hot=set(hot))


def build_print_html(r: Dict[str, Any]) -> str:
    generated = datetime.now().strftime("%d/%m/%Y à %H:%M")
    uri = _logo_data_uri()
    logo = f'<img class="logo" src="{uri}" alt="OLEA" />' if uri else '<b style="color:#b4482b;font-size:22px">OLEA</b>'
    head = f'<table class="print-header"><tr><td>{logo}</td><td class="r">{_esc(r["entete"])}</td></tr></table>'
    foot = "<footer>Document généré par OLEA Finance</footer>"

    def sheet(*parts) -> str:
        return f'<section class="sheet">{head}{"".join(parts)}{foot}</section>'

    meta = ('<table class="meta"><tr>'
            f'<td><small>SITUATION AU</small><strong>{_d(r["date_reference"])}</strong></td>'
            f'<td><small>SOURCE</small><strong>{_esc(_short(r["fichier"]))}</strong></td>'
            f'<td><small>DATE D\'ÉDITION</small><strong>{generated}</strong></td>'
            f'<td><small>{_esc(r["tiers_pl"].upper())}</small><strong>{r["nb"]}</strong></td></tr></table>')
    kpis = _h_table(["Indicateur", "Montant (TND)", "Détail"], [[_esc(k), _m(v), _esc(c)] for k, v, c in r["kpis"]], num_to=2)
    first = [f'<div class="eyebrow">RAPPORT DE PILOTAGE</div><h1>{_esc(r["titre"])}</h1>', meta, "<h2>Synthèse</h2>", kpis, _h_aging(r["aging"])]
    if r["aging_contre"]["total"] > 0.0005:
        first.append(_h_aging(r["aging_contre"]))
    sheets = [sheet(*first)]

    tiers_html = _h_tiers(r["principal"], r["tiers"]) if r["principal"]["rows"] else f"<h2>{_esc(r['principal']['titre'])}</h2><p class='note'>Aucune donnée dans cette catégorie.</p>"
    if r["contre"]["rows"]:
        tiers_html += _h_tiers(r["contre"], r["tiers"])
    if r["autres"]:
        rows = [[f'<b>{_esc(x["nom"])}</b><div class="code">{_esc(x["code"])}</div>', _z(x["x"][0]), _z(x["x"][1])] for x in r["autres"]["rows"]]
        tiers_html += f"<h2>{_esc(r['autres']['titre'])} ({len(rows)})</h2>" + _h_table([r["tiers"], "FNP (408)", "Avances (409)"], rows)
    sheets.append(sheet(tiers_html))

    if r["ecritures"]:
        rows, bands = [], []
        for g in r["ecritures"]:
            bands.append(len(rows))
            rows.append([f'<b>{_esc(g["nom"])}</b> <span class="code">{_esc(g["code"])}</span>'])
            for d_, lib, nat, deb, cre, reste, jours, lab in g["rows"]:
                rows.append([d_, _esc(lib), _esc(nat), _z(deb), _z(cre), _m(reste), f"{jours} j", lab])
        sheets.append(sheet(f"<h2>Écritures ouvertes par {_esc(r['tiers'].lower())}</h2>",
                            "<p class='note'>Écritures non soldées après imputation des règlements sur les pièces les plus anciennes (FIFO).</p>",
                            _h_table(["Date", "Libellé", "Nature", "Débit", "Crédit", "Reste", "Ancienneté", "Tranche"], rows, num_from=3, num_to=7, bands=set(bands))))

    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8" /><title>Impression {_esc(r["titre"])}</title>'
            f"<style>{_CSS}</style></head><body>{''.join(sheets)}</body></html>")


# ───────────────────────── Prévisualisation (JSON, rendue par le frontend comme dans Reporting) ─────────────────────────
def build_sections(r: Dict[str, Any]) -> Dict[str, Any]:
    """Même contenu que le PDF : sections {title, headers, align, rows, row_classes, cell_classes, spans, note}."""
    def sec(title, headers, rows, align, classes=None, cells=None, spans=None, note=None):
        return {"title": title, "headers": headers, "align": align, "rows": rows,
                "row_classes": classes or [""] * len(rows), "cell_classes": cells, "spans": spans or [], "note": note}

    def aging(a):
        total = a["total"] or 0.0
        rows = [[lab, _m(a["buckets"].get(k, 0.0)), _pct(a["buckets"].get(k, 0.0), total)] for k, lab in zip(BUCKET_KEYS, BUCKET_LABELS)]
        rows.append(["Total", _m(total), "100 %" if total > 0 else "0 %"])
        return sec(a["titre"], ["Tranche", "Montant (TND)", "% du total"], rows, ["l", "r", "r"], [""] * 5 + ["row-result"])

    def tiers(blk):
        heads = [r["tiers"], "Solde", *BUCKET_LABELS, *blk["extra"]]
        rows, cells, sums = [], [], [0.0] * (len(heads) - 1)
        for x in blk["rows"]:
            vals = [x["solde"], *x["b"], *x["x"]]
            rows.append([f'{x["nom"]} · {x["code"]}', _m(vals[0]), *[_z(v) for v in vals[1:]]])
            cells.append(["", "", "", "", "", "", "ba-hot" if x["b"][4] > 0.0005 else ""] + [""] * len(blk["extra"]))
            for i, v in enumerate(vals):
                sums[i] += v
        rows.append(["Total", *[_m(v) for v in sums]])
        cells.append([""] * len(heads))
        return sec(f"{blk['titre']} ({len(blk['rows'])})", heads, rows, ["l"] + ["r"] * (len(heads) - 1),
                   [""] * (len(rows) - 1) + ["row-result"], cells)

    sections = [sec("Synthèse", ["Indicateur", "Montant (TND)", "Détail"], [[k, _m(v), c] for k, v, c in r["kpis"]], ["l", "r", "l"]),
                aging(r["aging"])]
    if r["aging_contre"]["total"] > 0.0005:
        sections.append(aging(r["aging_contre"]))
    if r["principal"]["rows"]:
        sections.append(tiers(r["principal"]))
    else:
        sections.append(sec(r["principal"]["titre"], [], [], []))
    if r["contre"]["rows"]:
        sections.append(tiers(r["contre"]))
    if r["autres"]:
        rows = [[f'{x["nom"]} · {x["code"]}', _z(x["x"][0]), _z(x["x"][1])] for x in r["autres"]["rows"]]
        sections.append(sec(f"{r['autres']['titre']} ({len(rows)})", [r["tiers"], "FNP (408)", "Avances (409)"], rows, ["l", "r", "r"]))
    if r["ecritures"]:
        rows, classes, spans = [], [], []
        for g in r["ecritures"]:
            spans.append(len(rows))
            rows.append([f'{g["nom"]} · {g["code"]}'] + [""] * 7)
            classes.append("row-agg")
            for d_, lib, nat, deb, cre, reste, jours, lab in g["rows"]:
                rows.append([d_, lib, nat, _z(deb), _z(cre), _m(reste), f"{jours} j", lab])
                classes.append("")
        sections.append(sec(f"Écritures ouvertes par {r['tiers'].lower()}",
                            ["Date", "Libellé", "Nature", "Débit", "Crédit", "Reste", "Ancienneté", "Tranche"], rows,
                            ["l", "l", "l", "r", "r", "r", "r", "l"], classes, spans=spans,
                            note="Écritures non soldées après imputation des règlements sur les pièces les plus anciennes (FIFO)."))
    return {"titre": r["titre"], "entete": r["entete"], "date_reference": _d(r["date_reference"]),
            "fichier": _short(r["fichier"], 34), "generated_at": datetime.now().strftime("%d/%m/%Y à %H:%M"),
            "tiers_pl": r["tiers_pl"], "nb": r["nb"], "sections": sections}