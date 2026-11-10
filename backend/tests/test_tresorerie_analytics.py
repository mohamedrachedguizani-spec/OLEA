"""
Agrégations de l'analyse graphique du module Trésorerie.

Deux garanties que ces tests protègent :
  - le dernier point d'une courbe de solde égale le solde du reporting (KPI) ;
  - les jours sans mouvement reportent la dernière valeur, sans redescente à zéro.
"""

import unittest
from datetime import date, timedelta

from modules.tresorerie.service import (
    agreger_flux_par_periode,
    calculer_solde,
    cle_periode,
    construire_serie_soldes,
    construire_serie_totale,
    echantillonner_serie,
    normaliser_granularite,
)


def _mv(compte, jour, debit=0.0, credit=0.0):
    return {"compte_banque": compte, "date_operation": jour, "debit": debit, "credit": credit}


class TestGranularite(unittest.TestCase):
    def test_valeurs_acceptees(self):
        for valeur in ("jour", "semaine", "mois", " JOUR "):
            self.assertIn(normaliser_granularite(valeur), ("jour", "semaine", "mois"))

    def test_defaut_est_jour(self):
        self.assertEqual(normaliser_granularite(None), "jour")
        self.assertEqual(normaliser_granularite(""), "jour")

    def test_valeur_invalide_leve(self):
        with self.assertRaises(ValueError):
            normaliser_granularite("annee")

    def test_cle_semaine_est_le_lundi(self):
        # 8 octobre 2026 est un jeudi : sa semaine commence le lundi 5.
        self.assertEqual(cle_periode(date(2026, 10, 8), "semaine"), date(2026, 10, 5))

    def test_cle_mois_est_le_premier_jour(self):
        self.assertEqual(cle_periode(date(2026, 10, 8), "mois"), date(2026, 10, 1))

    def test_cle_jour_inchangee(self):
        self.assertEqual(cle_periode(date(2026, 10, 8), "jour"), date(2026, 10, 8))


class TestAgregationFlux(unittest.TestCase):
    def setUp(self):
        self.mouvements = [
            _mv("TN-ATB1", date(2026, 10, 1), debit=100, credit=0),
            _mv("TN-ATB1", date(2026, 10, 1), credit=500),
            _mv("UB1", date(2026, 10, 2), debit=30),
            _mv("TN-ATB1", date(2026, 10, 8), credit=200),
        ]

    def test_regroupe_par_jour(self):
        flux = agreger_flux_par_periode(self.mouvements)
        self.assertEqual(len(flux), 3)
        premier = flux[0]
        self.assertEqual(premier["recette"], 500)
        self.assertEqual(premier["depense"], 100)
        self.assertEqual(premier["net"], 400)
        self.assertEqual(premier["nb_mouvements"], 2)

    def test_detail_par_banque(self):
        flux = agreger_flux_par_periode(self.mouvements)
        self.assertEqual(flux[1]["par_banque"]["UB1"]["depense"], 30)
        self.assertEqual(flux[1]["par_banque"]["UB1"]["net"], -30)

    def test_filtre_banque(self):
        flux = agreger_flux_par_periode(self.mouvements, compte_banque="UB1")
        self.assertEqual(len(flux), 1)
        self.assertEqual(flux[0]["depense"], 30)

    def test_semaine_et_mois_conservent_le_total(self):
        total_jour = sum(p["recette"] for p in agreger_flux_par_periode(self.mouvements, "jour"))
        for granularite in ("semaine", "mois"):
            flux = agreger_flux_par_periode(self.mouvements, granularite)
            self.assertAlmostEqual(sum(p["recette"] for p in flux), total_jour, places=3)

    def test_mouvement_sans_date_ignore(self):
        flux = agreger_flux_par_periode([_mv("UB1", None, credit=10)])
        self.assertEqual(flux, [])


class TestSerieSoldes(unittest.TestCase):
    ANCRES = {"TN-ATB1": {"solde": 1000.0, "date_solde": date(2026, 9, 30)}}

    def setUp(self):
        self.mouvements = [
            _mv("TN-ATB1", date(2026, 10, 1), debit=100),
            _mv("TN-ATB1", date(2026, 10, 1), credit=500),
            _mv("TN-ATB1", date(2026, 10, 8), credit=200),
        ]

    def test_dernier_point_egale_le_solde_du_reporting(self):
        serie = construire_serie_soldes(self.mouvements, self.ANCRES)["series"]["TN-ATB1"]
        net = sum(m["credit"] - m["debit"] for m in self.mouvements)
        self.assertAlmostEqual(serie[-1]["solde"], calculer_solde(1000.0, net), places=3)

    def test_jours_sans_mouvement_reportent_la_valeur(self):
        serie = construire_serie_soldes(self.mouvements, self.ANCRES)["series"]["TN-ATB1"]
        par_jour = {p["date"]: p["solde"] for p in serie}
        # 2, 3 et 4 octobre n'ont aucun mouvement : le solde du 1er est reporté.
        self.assertEqual(par_jour[date(2026, 10, 2)], 1400.0)
        self.assertEqual(par_jour[date(2026, 10, 4)], 1400.0)

    def test_banque_sans_ancre_exclue(self):
        resultat = construire_serie_soldes(
            self.mouvements + [_mv("UB1", date(2026, 10, 2), debit=5)],
            self.ANCRES,
        )
        self.assertIn("UB1", resultat["sans_solde"])
        self.assertNotIn("UB1", resultat["series"])

    def test_ancre_sans_solde_exclue(self):
        resultat = construire_serie_soldes(
            self.mouvements,
            {"TN-ATB1": {"solde": None, "date_solde": date(2026, 9, 30)}},
        )
        self.assertEqual(resultat["series"], {})
        self.assertEqual(resultat["sans_solde"], ["TN-ATB1"])

    def test_borne_du_respectee(self):
        serie = construire_serie_soldes(
            self.mouvements, self.ANCRES, date_debut=date(2026, 10, 5)
        )["series"]["TN-ATB1"]
        self.assertEqual(serie[0]["date"], date(2026, 10, 5))
        # Le solde antérieur est intégré au premier point, pas perdu.
        self.assertEqual(serie[0]["solde"], 1400.0)

    def test_borne_au_respectee(self):
        serie = construire_serie_soldes(
            self.mouvements, self.ANCRES, date_fin=date(2026, 10, 3)
        )["series"]["TN-ATB1"]
        self.assertEqual(serie[-1]["date"], date(2026, 10, 3))
        self.assertEqual(serie[-1]["solde"], 1400.0)

    def test_mouvements_anterieurs_a_l_ancre_ignores(self):
        mouvements = self.mouvements + [_mv("TN-ATB1", date(2026, 9, 15), credit=9999)]
        serie = construire_serie_soldes(mouvements, self.ANCRES)["series"]["TN-ATB1"]
        self.assertEqual(serie[0]["solde"], 1000.0)


class TestSerieTotale(unittest.TestCase):
    """Courbe « Toutes banques » : un seul solde cumulé, pas des courbes empilées."""

    def setUp(self):
        self.series = {
            "A": [{"date": date(2026, 9, 30), "solde": 1000.0},
                  {"date": date(2026, 10, 1), "solde": 1100.0}],
            "B": [{"date": date(2026, 10, 1), "solde": 500.0},
                  {"date": date(2026, 10, 2), "solde": 550.0}],
        }

    def test_une_seule_valeur_par_date(self):
        total = construire_serie_totale(self.series)
        dates = [p["date"] for p in total]
        self.assertEqual(len(dates), len(set(dates)))

    def test_total_est_la_somme_des_banques_connues(self):
        total = construire_serie_totale(self.series)
        par_date = {p["date"]: p["solde"] for p in total}
        # Le 30/09, seule A est connue : le total vaut 1000, pas 1500.
        self.assertEqual(par_date[date(2026, 9, 30)], 1000.0)
        self.assertEqual(par_date[date(2026, 10, 1)], 1600.0)
        self.assertEqual(par_date[date(2026, 10, 2)], 1650.0)

    def test_dernier_point_egale_la_somme_des_derniers_soldes(self):
        total = construire_serie_totale(self.series)
        attendu = sum(points[-1]["solde"] for points in self.series.values())
        self.assertAlmostEqual(total[-1]["solde"], attendu, places=3)

    def test_banque_absente_d_une_date_garde_sa_derniere_valeur(self):
        series = {
            "A": [{"date": date(2026, 10, 1), "solde": 100.0},
                  {"date": date(2026, 10, 2), "solde": 200.0},
                  {"date": date(2026, 10, 3), "solde": 300.0}],
            # B s'arrête le 1er (borne « Au » de son relevé).
            "B": [{"date": date(2026, 10, 1), "solde": 50.0}],
        }
        par_date = {p["date"]: p["solde"] for p in construire_serie_totale(series)}
        self.assertEqual(par_date[date(2026, 10, 3)], 350.0)  # 300 + 50 reporté

    def test_series_vides(self):
        self.assertEqual(construire_serie_totale({}), [])
        self.assertEqual(construire_serie_totale({"A": []}), [])


class TestEchantillonnage(unittest.TestCase):
    """La courbe de solde doit suivre la granularité, comme les barres."""

    def setUp(self):
        # 40 jours consécutifs, solde croissant de 10 par jour.
        self.points = [
            {"date": date(2026, 9, 29) + timedelta(days=i), "solde": 1000.0 + i * 10}
            for i in range(40)
        ]

    def test_jour_ne_change_rien(self):
        self.assertEqual(echantillonner_serie(self.points, "jour"), self.points)

    def test_derniere_valeur_toujours_conservee(self):
        for granularite in ("semaine", "mois"):
            points = echantillonner_serie(self.points, granularite)
            self.assertEqual(points[-1]["solde"], self.points[-1]["solde"])

    def test_dates_alignees_sur_la_cle_de_periode(self):
        for granularite in ("semaine", "mois"):
            points = echantillonner_serie(self.points, granularite)
            for point in points:
                self.assertEqual(point["date"], cle_periode(point["date"], granularite))

    def test_reduction_du_nombre_de_points(self):
        jour = len(echantillonner_serie(self.points, "jour"))
        semaine = len(echantillonner_serie(self.points, "semaine"))
        mois = len(echantillonner_serie(self.points, "mois"))
        self.assertGreater(jour, semaine)
        self.assertGreater(semaine, mois)

    def test_serie_vide(self):
        self.assertEqual(echantillonner_serie([], "mois"), [])


if __name__ == "__main__":
    unittest.main()