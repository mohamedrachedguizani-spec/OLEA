import importlib
import io
import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from fastapi import HTTPException

# `modules.tresorerie.router` est masqué par l'attribut `router` du paquet :
# l'import par attribut renvoie l'APIRouter, pas le module. On importe donc le module.
treso_router = importlib.import_module("modules.tresorerie.router")
from modules.tresorerie.models import BulkNatureUpdateRequest


class SequencedCursor:
    """Cursor factice qui rejoue des réponses dans l'ordre des SELECT."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.queries = []
        self.params = []
        self._current = None
        self.rowcount = 0
        self.lastrowid = 1
        self.inserted_rows = []

    def execute(self, query, params=()):
        self.queries.append(" ".join(query.split()))
        self.params.append(tuple(params or ()))
        self._current = None
        # Seules les requêtes de lecture consomment une réponse programmée.
        if "select" in query.lower():
            self._current = self.responses.pop(0) if self.responses else []

    def executemany(self, query, seq_params):
        self.queries.append(" ".join(query.split()))
        self.inserted_rows.extend(tuple(p) for p in seq_params)
        self._current = []

    def fetchone(self):
        if isinstance(self._current, list):
            return self._current[0] if self._current else None
        return self._current

    def fetchall(self):
        return self._current if isinstance(self._current, list) else []


class FakeUpload:
    """UploadFile minimal pour appeler directement l'endpoint d'import."""

    def __init__(self, filename="releve.csv", content=b"date;libelle;debit;credit\n"):
        self.filename = filename
        self.content_type = "text/csv"
        self.file = io.BytesIO(content)


def _cursor_context(cursor):
    @contextmanager
    def context():
        yield cursor
    return context


class TestMouvementsFiltres(unittest.TestCase):
    def _appel(self, cursor, **kwargs):
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)):
            return treso_router.lister_mouvements(**kwargs)

    def test_filtre_periode_produit_des_conditions_valides(self):
        cursor = SequencedCursor([
            [{"cnt": 0}],   # COUNT
            [],             # page
            [],             # compteurs
        ])
        self._appel(
            cursor,
            date_debut=date(2026, 5, 1),
            date_fin=date(2026, 5, 31),
            nature="exploitation",
        )
        requete_count = cursor.queries[0]
        self.assertIn("m.date_operation >= %s", requete_count)
        self.assertIn("m.date_operation <= %s", requete_count)
        self.assertIn("m.nature = %s", requete_count)
        self.assertNotIn("1=1 AND 1=1", requete_count)
        self.assertNotIn("AND  AND", requete_count)
        self.assertEqual(
            cursor.params[0],
            (date(2026, 5, 1), date(2026, 5, 31), "exploitation"),
        )

    def test_compteurs_ignorent_le_filtre_de_nature(self):
        cursor = SequencedCursor([
            [{"cnt": 3}],
            [],
            [
                {"nature": "exploitation", "nb": 2},
                {"nature": "non_classe", "nb": 1},
            ],
        ])
        resultat = self._appel(cursor, nature="exploitation")
        # La requête des compteurs ne doit pas filtrer sur la nature…
        self.assertNotIn("m.nature = %s", cursor.queries[2])
        # … mais la requête paginée, si.
        self.assertIn("m.nature = %s", cursor.queries[0])
        self.assertEqual(resultat["compteurs"]["exploitation"], 2)
        self.assertEqual(resultat["compteurs"]["non_classe"], 1)
        self.assertEqual(resultat["compteurs"]["commission"], 0)
        self.assertEqual(resultat["compteurs"]["hors_exploitation"], 0)

    def test_filtre_non_classe_utilise_is_null(self):
        cursor = SequencedCursor([[{"cnt": 0}], [], []])
        self._appel(cursor, nature="non_classe")
        self.assertIn("m.nature IS NULL", cursor.queries[0])
        self.assertNotIn("%s", cursor.queries[0].split("WHERE")[-1].replace("IS NULL", ""))

    def test_recherche_porte_sur_libelle_et_reference(self):
        cursor = SequencedCursor([[{"cnt": 0}], [], []])
        self._appel(cursor, search="virement")
        self.assertIn("m.libelle LIKE %s OR m.reference LIKE %s", cursor.queries[0])
        self.assertIn("%virement%", cursor.params[0])

    def test_sans_filtre_aucune_condition_superflue(self):
        cursor = SequencedCursor([[{"cnt": 0}], [], []])
        self._appel(cursor)
        self.assertIn("WHERE 1=1", cursor.queries[0])
        self.assertNotIn("%s", cursor.queries[0].split("WHERE")[-1])


class TestClassementLot(unittest.TestCase):
    def test_refuse_un_lot_vide(self):
        with self.assertRaises(HTTPException) as raised:
            treso_router.classer_mouvements(
                BulkNatureUpdateRequest(movement_ids=[], nature="exploitation"),
                request=None,
                user={"id": 1, "username": "test"},
            )
        self.assertEqual(raised.exception.status_code, 400)

    def test_refuse_une_nature_inconnue(self):
        with self.assertRaises(HTTPException) as raised:
            treso_router.classer_mouvements(
                BulkNatureUpdateRequest(movement_ids=[1, 2], nature="inconnue"),
                request=None,
                user={"id": 1, "username": "test"},
            )
        self.assertEqual(raised.exception.status_code, 400)

    def test_applique_la_nature_au_lot(self):
        cursor = SequencedCursor([[]])
        cursor.rowcount = 2
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)), \
             patch.object(treso_router, "log_audit_action"), \
             patch.object(treso_router, "ws_manager"):
            resultat = treso_router.classer_mouvements(
                BulkNatureUpdateRequest(movement_ids=[1, 2], nature="commission"),
                request=None,
                user={"id": 1, "username": "test"},
            )
        self.assertEqual(resultat, {"updated": 2, "nature": "commission"})
        self.assertIn("UPDATE tresorerie_movements", cursor.queries[-1])
        self.assertEqual(cursor.params[-1][0], "commission")

    def test_declassement_remet_la_nature_a_null(self):
        cursor = SequencedCursor([[]])
        cursor.rowcount = 1
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)), \
             patch.object(treso_router, "log_audit_action"), \
             patch.object(treso_router, "ws_manager"):
            resultat = treso_router.classer_mouvements(
                BulkNatureUpdateRequest(movement_ids=[5], nature=None),
                request=None,
                user={"id": 1, "username": "test"},
            )
        self.assertEqual(resultat, {"updated": 1, "nature": None})
        self.assertIsNone(cursor.params[-1][0])


class FakeDf:
    def __init__(self, size=3):
        self.index = list(range(size))


def _mouvement(quand, libelle="VIREMENT CLIENT", debit=0.0, credit=100.0):
    return {
        "date_operation": quand,
        "libelle": libelle,
        "reference": None,
        "debit": debit,
        "credit": credit,
    }


class TestParseDateIso(unittest.TestCase):
    """Les dates du formulaire (AAAA-MM-JJ) ne doivent pas être lues en « jour d'abord ».

    `_parse_date` du module Saisie caisse utilise dateutil avec dayfirst=True :
    il lit « 2026-01-10 » comme le 1er octobre. Le parseur ISO de l'import
    doit renvoyer le 10 janvier.
    """

    def test_mois_et_jour_ne_sont_pas_inverses(self):
        self.assertEqual(treso_router._parse_date_iso("2026-01-10"), date(2026, 1, 10))
        self.assertEqual(treso_router._parse_date_iso("2026-02-03"), date(2026, 2, 3))
        self.assertEqual(treso_router._parse_date_iso("2026-12-31"), date(2026, 12, 31))

    def test_valeur_vide_ou_absente(self):
        self.assertIsNone(treso_router._parse_date_iso(""))
        self.assertIsNone(treso_router._parse_date_iso("   "))
        self.assertIsNone(treso_router._parse_date_iso(None))

    def test_repli_sur_un_format_non_iso(self):
        self.assertEqual(treso_router._parse_date_iso("10/01/2026"), date(2026, 1, 10))


class TestImportPeriode(unittest.TestCase):
    """Import : périodes obligatoires, filtrage sur la période et anti-doublon."""

    def _importer(self, cursor=None, mouvements=None, periodes=("2026-01-01", "2026-01-10"), **kwargs):
        cursor = cursor or SequencedCursor([])
        mouvements = mouvements if mouvements is not None else [
            _mouvement(date(2026, 1, 5)),
        ]
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)), \
             patch.object(treso_router, "_parse_csv_text", return_value=FakeDf()), \
             patch.object(treso_router, "_extract_movements", return_value=list(mouvements)), \
             patch.object(treso_router, "log_audit_action"), \
             patch.object(treso_router, "ws_manager"):
            return treso_router.importer_extrait(
                request=None,
                file=FakeUpload(),
                compte_banque=kwargs.pop("compte_banque", "BI1"),
                periode_debut=periodes[0],
                periode_fin=periodes[1],
                user={"id": 1, "username": "test"},
                **kwargs,
            )

    def test_periode_obligatoire(self):
        for debut, fin in ((None, "2026-01-10"), ("2026-01-01", None), ("", "")):
            with self.subTest(debut=debut, fin=fin):
                with self.assertRaises(HTTPException) as raised:
                    self._importer(periodes=(debut, fin))
                self.assertEqual(raised.exception.status_code, 400)
                self.assertIn("obligatoires", raised.exception.detail)

    def test_periode_invalide(self):
        with self.assertRaises(HTTPException) as raised:
            self._importer(periodes=("pas-une-date", "2026-01-10"))
        self.assertEqual(raised.exception.status_code, 400)

    def test_debut_apres_fin_refuse(self):
        with self.assertRaises(HTTPException) as raised:
            self._importer(periodes=("2026-01-10", "2026-01-01"))
        self.assertEqual(raised.exception.status_code, 400)

    def test_mouvements_hors_periode_ignores(self):
        cursor = SequencedCursor([
            [],                                        # contrôle anti-doublon
            {"id": 1, "compte_banque": "BI1"},         # entête relue
            [],                                        # aperçu
        ])
        resultat = self._importer(
            cursor=cursor,
            mouvements=[
                _mouvement(date(2026, 1, 1)),
                _mouvement(date(2026, 1, 5)),
                _mouvement(date(2026, 1, 10)),
                _mouvement(date(2026, 1, 11)),
                _mouvement(date(2025, 12, 31)),
            ],
        )
        # Seuls les 3 mouvements de la période sont conservés
        self.assertEqual(resultat["total_mouvements"], 3)
        dates = [ligne[1] for ligne in cursor.inserted_rows]
        self.assertEqual(dates, [date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 10)])
        # Le contrôle d'extraction signale les lignes écartées
        self.assertEqual(resultat["controle_extraction"]["lignes_extraites"], 3)
        self.assertTrue(any("hors période" in m for m in resultat["controle_extraction"]["messages"]))

    def test_aucun_mouvement_dans_la_periode_refuse(self):
        with self.assertRaises(HTTPException) as raised:
            self._importer(
                mouvements=[_mouvement(date(2025, 12, 20)), _mouvement(date(2026, 2, 2))],
            )
        self.assertEqual(raised.exception.status_code, 422)
        # Le message aide l'utilisateur en rappelant la couverture du relevé
        self.assertIn("20/12/2025", raised.exception.detail)
        self.assertIn("02/02/2026", raised.exception.detail)

    def test_chevauchement_refuse_avec_409(self):
        cursor = SequencedCursor([
            [{
                "id": 7,
                "file_name": "janvier.csv",
                "periode_debut": date(2026, 1, 1),
                "periode_fin": date(2026, 1, 5),
            }],
        ])
        with self.assertRaises(HTTPException) as raised:
            self._importer(cursor=cursor, periodes=("2026-01-04", "2026-01-08"))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("BI1", raised.exception.detail)
        self.assertIn("janvier.csv", raised.exception.detail)
        # Rien ne doit avoir été inséré
        self.assertEqual(cursor.inserted_rows, [])

    def test_periode_disjointe_acceptee(self):
        cursor = SequencedCursor([
            [{
                "id": 7,
                "file_name": "janvier.csv",
                "periode_debut": date(2026, 1, 1),
                "periode_fin": date(2026, 1, 5),
            }],
            {"id": 8, "compte_banque": "BI1"},
            [],
        ])
        resultat = self._importer(
            cursor=cursor,
            mouvements=[_mouvement(date(2026, 1, 8))],
            periodes=("2026-01-06", "2026-01-10"),
        )
        self.assertEqual(resultat["total_mouvements"], 1)

    def test_chevauchement_ignore_l_import_remplace(self):
        # Le remplacement exclut l'import existant du contrôle : ses dates ne bloquent pas.
        cursor = SequencedCursor([
            [],                          # contrôle anti-doublon (import remplacé exclu en SQL)
            [{"id": 7}],                 # l'import à remplacer existe
            {"id": 8, "compte_banque": "BI1"},
            [],
        ])
        resultat = self._importer(cursor=cursor, periodes=("2026-01-01", "2026-01-05"), remplacer_import_id=7)
        self.assertEqual(resultat["total_mouvements"], 1)
        # La requête anti-doublon exclut bien l'import remplacé
        self.assertIn("id <> %s", cursor.queries[0])

    def test_banque_invalide(self):
        with self.assertRaises(HTTPException) as raised:
            self._importer(compte_banque="XX9")
        self.assertEqual(raised.exception.status_code, 400)


class TestReportingEndpoint(unittest.TestCase):
    def test_statut_incomplet_si_mouvements_non_classes(self):
        cursor = SequencedCursor([
            [
                {"compte_banque": "BI1", "nature": "exploitation", "debit": 0, "credit": 100},
                {"compte_banque": "BI1", "nature": None, "debit": 20, "credit": 0},
            ],
            [{"nb": 2, "debit": 20, "credit": 100}],
        ])
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)):
            rapport = treso_router.get_reporting(date_debut=None, date_fin=None, compte_banque=None)
        self.assertEqual(rapport["totaux"]["recette_exploitation"], 100.0)
        self.assertEqual(rapport["totaux"]["non_classe_count"], 1)
        self.assertEqual(rapport["controle"]["statut"], "INCOMPLET")
        self.assertEqual(rapport["controle"]["ecart_debit"], 0.0)
        self.assertEqual(rapport["controle"]["ecart_credit"], 0.0)

    def test_statut_ok_quand_tout_est_classe_et_coherent(self):
        cursor = SequencedCursor([
            [
                {"compte_banque": "BI2", "nature": "commission", "debit": 5, "credit": 0},
            ],
            [{"nb": 1, "debit": 5, "credit": 0}],
        ])
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)):
            rapport = treso_router.get_reporting(date_debut=None, date_fin=None, compte_banque=None)
        self.assertEqual(rapport["controle"]["statut"], "OK")
        bi2 = next(b for b in rapport["banques"] if b["compte_banque"] == "BI2")
        self.assertEqual(bi2["depense_exploitation"], 5.0)
        self.assertEqual(bi2["tresorerie_nette_exploitation"], -5.0)

    def test_filtre_banque_reduit_les_lignes_du_rapport(self):
        cursor = SequencedCursor([
            [{"compte_banque": "BI1", "nature": "exploitation", "debit": 0, "credit": 10}],
            [{"nb": 1, "debit": 0, "credit": 10}],
        ])
        with patch.object(treso_router.db, "get_cursor", _cursor_context(cursor)):
            rapport = treso_router.get_reporting(date_debut=None, date_fin=None, compte_banque="BI1")
        self.assertEqual([b["compte_banque"] for b in rapport["banques"]], ["BI1"])
        self.assertIn("i.compte_banque = %s", cursor.queries[0])


if __name__ == "__main__":
    unittest.main()
