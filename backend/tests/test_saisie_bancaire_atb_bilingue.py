"""
Extraction du relevé ATB « Relevé de compte » bilingue (mise en page 2026).

Ce format ne porte aucun en-tête de colonnes en texte (le bandeau est une
image) : les colonnes se lisent par position, et le sens débit/crédit vient de
l'alignement à droite du montant. Les PDF de test sont générés ici pour rester
reproductibles.
"""

import io
import unittest

from fastapi import HTTPException
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from modules.saisie_bancaire.service import (
    _extract_movements,
    _is_atb_bilingual_format,
    _parse_pdf,
    _parse_pdf_atb_bilingual,
)

# Colonnes du gabarit d'origine (A4, 595 pt de large) : le montant Débit est
# aligné à droite sur 358,4 pt et le montant Crédit sur 419,6 pt.
DEBIT_RIGHT = 358.4
CREDIT_RIGHT = 419.6
VAL_DATE_X = 268.4
REFERENCE_X = 203.6
LIBELLE_X = 74.0
JOUR_X = 59.6


def _amount(value: float) -> str:
    """9999999.999 -> '9.999.999,999' (format ATB)."""
    entier, _, decimales = f"{value:.3f}".partition(".")
    milliers = ""
    while len(entier) > 3:
        milliers = "." + entier[-3:] + milliers
        entier = entier[:-3]
    return f"{entier}{milliers},{decimales}"


def _build_pdf(lignes, opening=None, totals=None, closing=None, mois="Octobre 2026"):
    """
    lignes : (jour, libelle, reference, valeur, montant, colonne)
    colonne : 'debit' ou 'credit'
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Courier", 6)

    def new_page():
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(264.8, 842 - 75.2, mois + "  TUNIS SUD")
        pdf.drawString(286.4, 842 - 89.2, "094 1100 0030 84 / TND")
        pdf.drawString(63.2, 842 - 99.2, "OLEA TUNISIE")
        pdf.drawString(243.2, 842 - 109.2, "01 053 0941100003084 10")
        pdf.drawString(63.2, 842 - 119.2, "RUE KHAWAREZMI N17")
        pdf.drawString(221.6, 842 - 129.2, "TN59 0105 3094 1100 0030 8410")
        pdf.drawString(272.0, 842 - 143.2, "ATBKTNTT")
        pdf.setFont("Courier", 6)

    new_page()
    y = 183.2

    def line(y_pos, text, x, right_align=None):
        if right_align is None:
            pdf.drawString(x, 842 - y_pos, text)
        else:
            pdf.drawRightString(right_align, 842 - y_pos, text)

    if opening is not None:
        line(173.2, "Solde Au 30/09/2026", 124.4)
        line(173.2, _amount(opening), 0, right_align=CREDIT_RIGHT)

    for jour, libelle, reference, valeur, montant, colonne in lignes:
        line(y, jour, JOUR_X)
        line(y, libelle, LIBELLE_X)
        line(y, reference, REFERENCE_X)
        line(y, valeur, VAL_DATE_X)
        line(
            y, _amount(montant), 0,
            right_align=DEBIT_RIGHT if colonne == "debit" else CREDIT_RIGHT,
        )
        y += 10.0

    if totals is not None:
        y += 8
        line(y, "Totaux", 268.4)
        line(y, _amount(totals[0]), 0, right_align=DEBIT_RIGHT)
        line(y, _amount(totals[1]), 0, right_align=CREDIT_RIGHT)

    if closing is not None:
        y += 14
        suffixe = "CR" if closing >= 0 else ""
        line(y, "1", 70.4)
        line(y, "Solde Au 31/10/2026", 124.4)
        line(y, _amount(abs(closing)) + suffixe, 0, right_align=CREDIT_RIGHT)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


LIGNES = [
    ("01", "Tot Comm Trimest+TVA TOTAL COMM ..", "FT2627407LNM80R6", "01/10/26", 119.078, "debit"),
    ("01", "Vers esp Autre Ag-lassaad fkih ali", "TT26274CBY85", "02/10/26", 797.964, "credit"),
    ("01", "Tva sur Commission ves", "TT26274CBY85", "02/10/26", 0.380, "debit"),
    ("01", "Interets ..", "FT2627410NQX4280", "30/09/26", 160.092, "debit"),
    ("02", "Vers esp Autre Ag-Zaghouan", "TT26275FQMJB", "05/10/26", 1650.000, "credit"),
    ("06", "Virement Emis autres banques 06102", "FT262790X29B1WVK", "05/10/26", 30376.691, "debit"),
    ("30", "Vers esp MAG-MOLKA TAIEB", "TT26303DFDSL", "02/11/26", 1255.982, "credit"),
]
TOTAL_DEBIT = round(sum(x[4] for x in LIGNES if x[5] == "debit"), 3)
TOTAL_CREDIT = round(sum(x[4] for x in LIGNES if x[5] == "credit"), 3)
OPENING = 61276.857
CLOSING = round(OPENING + TOTAL_CREDIT - TOTAL_DEBIT, 3)


class TestDetectionFormat(unittest.TestCase):
    def test_detecte_le_nouveau_format(self):
        pdf = _build_pdf(LIGNES, opening=OPENING, totals=(TOTAL_DEBIT, TOTAL_CREDIT))
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            texte = "\n".join((page.extract_text() or "") for page in doc.pages)
        self.assertTrue(_is_atb_bilingual_format(texte))

    def test_ne_detecte_pas_un_texte_quelconque(self):
        self.assertFalse(_is_atb_bilingual_format("Releve de compte sans aucune ligne"))


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.pdf = _build_pdf(
            LIGNES,
            opening=OPENING,
            totals=(TOTAL_DEBIT, TOTAL_CREDIT),
            closing=CLOSING,
        )
        self.df = _parse_pdf_atb_bilingual(self.pdf)

    def test_toutes_les_lignes_sont_extraites(self):
        self.assertEqual(len(self.df), len(LIGNES))

    def test_sens_lu_dans_la_colonne(self):
        lignes = self.df.to_dict("records")
        credit = next(x for x in lignes if x["reference"].startswith("TT26274CBY"))
        self.assertEqual(credit["credit"], 797.964)
        self.assertEqual(credit["debit"], 0.0)
        debit = next(x for x in lignes if x["libelle"].startswith("Virement Emis"))
        self.assertEqual(debit["debit"], 30376.691)
        self.assertEqual(debit["credit"], 0.0)

    def test_totaux_egaux_au_releve(self):
        self.assertAlmostEqual(self.df["debit"].sum(), TOTAL_DEBIT, places=3)
        self.assertAlmostEqual(self.df["credit"].sum(), TOTAL_CREDIT, places=3)

    def test_date_operation_reconstruite_meme_quand_le_mois_differe(self):
        ligne = next(
            x for x in self.df.to_dict("records")
            if x["reference"] == "TT26303DFDSL"
        )
        # Jour 30, valeur 02/11/26 : l'opération est le 30/10, pas le 30/11.
        self.assertEqual(ligne["date_operation"].isoformat(), "2026-10-30")
        self.assertEqual(ligne["date_valeur"].isoformat(), "2026-11-02")

    def test_reference_et_libelle_propres(self):
        ligne = self.df.iloc[1]
        self.assertEqual(ligne["reference"], "TT26274CBY85")
        self.assertEqual(ligne["libelle"], "Vers esp Autre Ag-lassaad fkih ali")

    def test_extract_movements_conserve_les_lignes(self):
        mouvements = _extract_movements(self.df)
        self.assertEqual(len(mouvements), len(LIGNES))


class TestControles(unittest.TestCase):
    def test_refuse_un_total_imprime_different(self):
        pdf = _build_pdf(
            LIGNES,
            opening=OPENING,
            totals=(TOTAL_DEBIT, TOTAL_CREDIT + 1),
            closing=CLOSING,
        )
        with self.assertRaises(HTTPException) as ctx:
            _parse_pdf_atb_bilingual(pdf)
        self.assertIn("Écart de contrôle ATB", ctx.exception.detail)

    def test_refuse_un_solde_de_cloture_incoherent(self):
        pdf = _build_pdf(
            LIGNES,
            opening=OPENING,
            totals=(TOTAL_DEBIT, TOTAL_CREDIT),
            closing=CLOSING + 5,
        )
        with self.assertRaises(HTTPException) as ctx:
            _parse_pdf_atb_bilingual(pdf)
        self.assertIn("Écart de contrôle ATB", ctx.exception.detail)

    def test_accepte_quand_le_solde_reconcile(self):
        pdf = _build_pdf(
            LIGNES,
            opening=OPENING,
            totals=(TOTAL_DEBIT, TOTAL_CREDIT),
            closing=CLOSING,
        )
        self.assertEqual(len(_parse_pdf_atb_bilingual(pdf)), len(LIGNES))

    def test_detection_branchee_dans_le_parseur_general(self):
        pdf = _build_pdf(
            LIGNES,
            opening=OPENING,
            totals=(TOTAL_DEBIT, TOTAL_CREDIT),
            closing=CLOSING,
        )
        self.assertEqual(len(_parse_pdf(pdf)), len(LIGNES))


if __name__ == "__main__":
    unittest.main()
