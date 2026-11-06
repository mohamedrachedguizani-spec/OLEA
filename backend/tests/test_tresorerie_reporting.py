import unittest
from datetime import date

from modules.tresorerie.constants import (
    normaliser_nature,
    suggerer_nature,
    NATURE_COMMISSION,
    NATURE_EXPLOITATION,
    NATURE_HORS_EXPLOITATION,
)
from modules.tresorerie.service import (
    calculer_solde,
    ancre_de_banque,
    construire_controle_extraction,
    construire_reporting,
    cumuler_mouvement,
    demarrer_couverture,
    filtrer_mouvements_par_periode,
    nouveau_agregat,
    periodes_chevauchent,
    preparer_mouvements_extraits,
    totaliser,
    totaliser_commissions,
)


def _mov(compte, nature, debit=0.0, credit=0.0):
    return {"compte_banque": compte, "nature": nature, "debit": debit, "credit": credit}


class TestReglesReporting(unittest.TestCase):
    def test_commission_debit_comptee_dans_depense_exploitation(self):
        rapport = construire_reporting([
            _mov("BI1", NATURE_EXPLOITATION, credit=1000),
            _mov("BI1", NATURE_COMMISSION, debit=20),
        ])
        bi1 = next(b for b in rapport if b["compte_banque"] == "BI1")
        # Recette exploitation = exploitation + commissions créditrices
        self.assertEqual(bi1["recette_exploitation"], 1000.0)
        # Dépense exploitation = exploitation + commissions débitrices
        self.assertEqual(bi1["depense_exploitation"], 20.0)
        self.assertEqual(bi1["dont_depense_commission"], 20.0)
        self.assertEqual(bi1["tresorerie_nette_exploitation"], 980.0)

    def test_commission_credit_comptee_dans_recette_exploitation(self):
        rapport = construire_reporting([_mov("BI2", NATURE_COMMISSION, credit=15)])
        bi2 = next(b for b in rapport if b["compte_banque"] == "BI2")
        self.assertEqual(bi2["recette_exploitation"], 15.0)
        self.assertEqual(bi2["dont_recette_commission"], 15.0)
        self.assertEqual(bi2["depense_exploitation"], 0.0)

    def test_hors_exploitation_isole_de_exploitation(self):
        rapport = construire_reporting([
            _mov("UB1", NATURE_EXPLOITATION, credit=300),
            _mov("UB1", NATURE_HORS_EXPLOITATION, credit=500),
            _mov("UB1", NATURE_HORS_EXPLOITATION, debit=100),
        ])
        ub1 = next(b for b in rapport if b["compte_banque"] == "UB1")
        self.assertEqual(ub1["recette_exploitation"], 300.0)
        self.assertEqual(ub1["recette_hors_exploitation"], 500.0)
        self.assertEqual(ub1["depense_hors_exploitation"], 100.0)
        self.assertEqual(ub1["tresorerie_nette_hors_exploitation"], 400.0)

    def test_mouvement_non_classe_exclu_des_ratios_mais_compte(self):
        rapport = construire_reporting([_mov("BI3", None, debit=50)])
        bi3 = next(b for b in rapport if b["compte_banque"] == "BI3")
        self.assertEqual(bi3["non_classe_count"], 1)
        self.assertEqual(bi3["non_classe_debit"], 50.0)
        self.assertEqual(bi3["recette_exploitation"], 0.0)
        self.assertEqual(bi3["depense_exploitation"], 0.0)
        self.assertEqual(bi3["total_debit"], 50.0)

    def test_total_toutes_banques_est_la_somme_des_banques(self):
        rapport = construire_reporting([
            _mov("BI1", NATURE_EXPLOITATION, credit=100),
            _mov("BI2", NATURE_EXPLOITATION, credit=250),
            _mov("UB1", NATURE_COMMISSION, debit=10),
        ])
        total = totaliser(rapport)
        self.assertEqual(total["recette_exploitation"], 350.0)
        self.assertEqual(total["depense_exploitation"], 10.0)
        self.assertEqual(total["tresorerie_nette_exploitation"], 340.0)
        self.assertEqual(total["nb_mouvements"], 3)

    def test_toutes_les_banques_du_referentiel_sont_presentes(self):
        rapport = construire_reporting([])
        codes = [b["compte_banque"] for b in rapport]
        self.assertIn("BI1", codes)
        self.assertIn("TN-ATB1", codes)
        self.assertIn("UB3", codes)
        self.assertTrue(all(b["nb_mouvements"] == 0 for b in rapport))

    def test_tresorerie_nette_negative(self):
        agregat = nouveau_agregat("BI1")
        cumuler_mouvement(agregat, {"debit": 100, "credit": 0, "nature": NATURE_EXPLOITATION})
        cumuler_mouvement(agregat, {"debit": 0, "credit": 40, "nature": NATURE_EXPLOITATION})
        finalise = construire_reporting([_mov("BI1", NATURE_EXPLOITATION, credit=40),
                                         _mov("BI1", NATURE_EXPLOITATION, debit=100)])[0]
        self.assertEqual(finalise["tresorerie_nette_exploitation"], -60.0)

    def test_montants_arrondis_au_millime(self):
        rapport = construire_reporting([_mov("BI1", NATURE_EXPLOITATION, credit=10.0004),
                                        _mov("BI1", NATURE_EXPLOITATION, credit=0.0004)])
        bi1 = rapport[0]
        self.assertEqual(bi1["recette_exploitation"], round(bi1["recette_exploitation"], 3))
        self.assertEqual(str(bi1["recette_exploitation"]).split(".")[-1].__len__() <= 3, True)


class TestNatures(unittest.TestCase):
    def test_normaliser_nature(self):
        self.assertEqual(normaliser_nature("exploitation"), NATURE_EXPLOITATION)
        self.assertEqual(normaliser_nature(" HORS_EXPLOITATION "), NATURE_HORS_EXPLOITATION)
        self.assertIsNone(normaliser_nature(None))
        self.assertIsNone(normaliser_nature(""))
        with self.assertRaises(ValueError):
            normaliser_nature("autre")

    def test_suggestion_commission(self):
        self.assertEqual(suggerer_nature("COMMISSION TENUE DE COMPTE", 12, 0), NATURE_COMMISSION)
        self.assertEqual(suggerer_nature("FRAIS BANCAIRES", 5, 0), NATURE_COMMISSION)

    def test_suggestion_hors_exploitation_avec_accents(self):
        self.assertEqual(suggerer_nature("PAIEMENT INTÉRÊTS DÉBITEURS", 20, 0), NATURE_HORS_EXPLOITATION)
        self.assertEqual(suggerer_nature("REMBOURSEMENT PRET", 500, 0), NATURE_HORS_EXPLOITATION)

    def test_suggestion_exploitation_par_defaut(self):
        self.assertEqual(suggerer_nature("VIREMENT RECU CLIENT", 0, 500), NATURE_EXPLOITATION)

    def test_suggestion_jamais_appliquee_d_office(self):
        prepares = preparer_mouvements_extraits([
            {"libelle": "COMMISSION TENUE DE COMPTE", "debit": 5, "credit": 0, "nature": None},
        ])
        self.assertEqual(prepares[0]["nature_suggeree"], NATURE_COMMISSION)
        self.assertIsNone(prepares[0]["nature"])


class TestPeriodes(unittest.TestCase):
    def test_chevauchement_inclusif_aux_bornes(self):
        jour = date
        # Périodes qui se touchent sur une même journée : doublon potentiel.
        self.assertTrue(periodes_chevauchent(
            jour(2026, 1, 1), jour(2026, 1, 10),
            jour(2026, 1, 10), jour(2026, 1, 20),
        ))
        # Inclusion totale.
        self.assertTrue(periodes_chevauchent(
            jour(2026, 1, 5), jour(2026, 1, 6),
            jour(2026, 1, 1), jour(2026, 1, 31),
        ))

    def test_periodes_disjointes(self):
        self.assertFalse(periodes_chevauchent(
            date(2026, 1, 1), date(2026, 1, 10),
            date(2026, 1, 11), date(2026, 1, 20),
        ))
        self.assertFalse(periodes_chevauchent(
            date(2026, 2, 1), date(2026, 2, 28),
            date(2026, 1, 1), date(2026, 1, 31),
        ))

    def test_periode_inconnue_ne_bloque_pas(self):
        self.assertFalse(periodes_chevauchent(
            date(2026, 1, 1), date(2026, 1, 10), None, date(2026, 1, 10),
        ))

    def test_filtre_inclusif_et_exclusion_hors_periode(self):
        mouvements = [
            {"date_operation": date(2026, 1, 1), "libelle": "debut"},
            {"date_operation": date(2026, 1, 5), "libelle": "dans"},
            {"date_operation": date(2026, 1, 10), "libelle": "fin"},
            {"date_operation": date(2026, 1, 11), "libelle": "apres"},
            {"date_operation": date(2025, 12, 31), "libelle": "avant"},
        ]
        dans, hors = filtrer_mouvements_par_periode(mouvements, date(2026, 1, 1), date(2026, 1, 10))
        self.assertEqual([m["libelle"] for m in dans], ["debut", "dans", "fin"])
        self.assertEqual([m["libelle"] for m in hors], ["apres", "avant"])

    def test_mouvement_sans_date_est_hors_periode(self):
        dans, hors = filtrer_mouvements_par_periode(
            [{"date_operation": None, "libelle": "inconnu"}],
            date(2026, 1, 1), date(2026, 1, 31),
        )
        self.assertEqual(dans, [])
        self.assertEqual(len(hors), 1)


class TestSoldeBanque(unittest.TestCase):
    """Le solde part d'une ancre figée par banque, lue une seule fois."""

    def _ancre(self, compte="BI1", solde=1000.0, date_solde=date(2026, 1, 1)):
        return {
            "compte_banque": compte,
            "solde": solde,
            "date_solde": date_solde,
            "source_file_name": "janvier.pdf",
        }

    def test_solde_est_ancre_plus_mouvements_nets(self):
        # 1 000 de départ, +200 de crédit, -50 de débit => 1 150
        self.assertEqual(calculer_solde(1000.0, 150.0), 1150.0)
        self.assertEqual(calculer_solde(-400.0, 100.0), -300.0)

    def test_solde_indisponible_sans_ancre(self):
        self.assertIsNone(calculer_solde(None, 150.0))

    def test_ancre_trouvee_pour_la_banque(self):
        ancres = [self._ancre("BI1", 1000.0), self._ancre("BI2", 5000.0)]
        self.assertEqual(ancre_de_banque(ancres, "BI1", date(2026, 2, 1))["solde"], 1000.0)
        self.assertEqual(ancre_de_banque(ancres, "BI2", date(2026, 2, 1))["solde"], 5000.0)

    def test_banque_sans_ancre_n_a_pas_de_solde(self):
        self.assertIsNone(ancre_de_banque([self._ancre("BI1")], "UB1", date(2026, 2, 1)))

    def test_ancre_posterieure_au_rapport_ignoree(self):
        # Une ancre au 1er mars ne doit pas servir pour un rapport arrêté au 28 février.
        ancres = [self._ancre("BI1", 1000.0, date(2026, 3, 1))]
        self.assertIsNone(ancre_de_banque(ancres, "BI1", date(2026, 2, 28)))

    def test_ancre_utilisable_sans_date_de_fin(self):
        ancres = [self._ancre("BI1", 1000.0, date(2026, 3, 1))]
        self.assertIsNotNone(ancre_de_banque(ancres, "BI1", None))

    def test_demarrage_utilise_la_date_du_solde(self):
        self.assertEqual(
            demarrer_couverture(self._ancre("BI1", 1000.0, date(2025, 12, 31))),
            date(2025, 12, 31),
        )

    def test_total_toutes_banques_somme_les_soldes(self):
        rapport = construire_reporting([_mov("BI1", NATURE_EXPLOITATION, credit=100)])
        rapport[0]["solde"] = 5000.0
        total = totaliser(rapport)
        self.assertEqual(total["solde"], 5000.0)

    def test_banque_sans_solde_reste_null(self):
        rapport = construire_reporting([_mov("BI1", NATURE_EXPLOITATION, credit=100)])
        self.assertIsNone(rapport[0]["solde"])
        self.assertIsNone(totaliser(rapport)["solde"])


class TestCommissions(unittest.TestCase):
    def test_synthese_par_banque_et_totaux(self):
        rapport = construire_reporting([
            _mov("BI1", NATURE_COMMISSION, debit=20, credit=0),
            _mov("BI1", NATURE_COMMISSION, debit=0, credit=5),
            _mov("BI2", NATURE_COMMISSION, debit=12),
            _mov("BI2", NATURE_EXPLOITATION, debit=100),
        ])
        synthese = totaliser_commissions(rapport)
        bi1 = next(b for b in synthese["par_banque"] if b["compte_banque"] == "BI1")
        bi2 = next(b for b in synthese["par_banque"] if b["compte_banque"] == "BI2")
        self.assertEqual(bi1["commissions_payees"], 20.0)
        self.assertEqual(bi1["commissions_encaissees"], 5.0)
        self.assertEqual(bi1["total_commissions"], 25.0)
        self.assertEqual(bi1["commissions_nettes"], -15.0)
        self.assertEqual(bi2["commissions_payees"], 12.0)
        self.assertEqual(bi2["commissions_encaissees"], 0.0)
        self.assertEqual(synthese["total_payees"], 32.0)
        self.assertEqual(synthese["total_encaissees"], 5.0)
        self.assertEqual(synthese["total_commissions"], 37.0)
        self.assertEqual(synthese["total_nettes"], -27.0)

    def test_banques_sans_commission_ont_des_zeros(self):
        rapport = construire_reporting([_mov("BI3", NATURE_EXPLOITATION, credit=100)])
        synthese = totaliser_commissions(rapport)
        bi3 = next(b for b in synthese["par_banque"] if b["compte_banque"] == "BI3")
        self.assertEqual(bi3["total_commissions"], 0.0)

    def test_liste_vide(self):
        synthese = totaliser_commissions([])
        self.assertEqual(synthese["par_banque"], [])
        self.assertEqual(synthese["total_commissions"], 0.0)


class TestControleExtraction(unittest.TestCase):
    def test_statut_ok_quand_tout_est_extrait(self):
        controle = construire_controle_extraction(
            fichier="releve.pdf",
            format_detecte="pdf",
            lignes_source=2,
            mouvements=[{"debit": 10, "credit": 0}, {"debit": 0, "credit": 5}],
        )
        self.assertEqual(controle["statut"], "OK")
        self.assertEqual(controle["total_debit"], 10.0)
        self.assertEqual(controle["total_credit"], 5.0)
        self.assertEqual(controle["lignes_extraites"], 2)

    def test_statut_warning_si_lignes_ignorees(self):
        controle = construire_controle_extraction(
            fichier="releve.csv",
            format_detecte="csv",
            lignes_source=5,
            mouvements=[{"debit": 10, "credit": 0}],
        )
        self.assertEqual(controle["statut"], "WARNING")
        self.assertEqual(controle["lignes_ignorees"], 4)
        self.assertTrue(controle["messages"])


if __name__ == "__main__":
    unittest.main()
