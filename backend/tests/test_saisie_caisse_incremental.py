import unittest
from datetime import date

from modules.saisie_caisse.router import (
    _is_position_before,
    get_update_recalc_pivot,
    recalculate_soldes_from,
)


class FakeCursor:
    """Cursor minimal pour tester recalculate_soldes_from sans base réelle."""

    def __init__(self, rows):
        # rows: list[dict] contenant id, date_ecriture, debit, credit, solde
        self.rows = [dict(r) for r in rows]
        self._last = None

    def execute(self, query, params=None):
        q = " ".join(query.strip().split()).lower()

        if q.startswith("select solde from ecritures_caisse where date_ecriture < %s"):
            start_date, _same_date, start_id = params
            candidates = [
                r for r in self.rows
                if (r["date_ecriture"] < start_date)
                or (r["date_ecriture"] == start_date and r["id"] < start_id)
            ]
            candidates.sort(key=lambda r: (r["date_ecriture"], r["id"]), reverse=True)
            self._last = candidates[0] if candidates else None
            return

        if q.startswith("select id, debit, credit from ecritures_caisse where date_ecriture > %s"):
            start_date, _same_date, start_id = params
            impacted = [
                {"id": r["id"], "debit": r["debit"], "credit": r["credit"]}
                for r in self.rows
                if (r["date_ecriture"] > start_date)
                or (r["date_ecriture"] == start_date and r["id"] >= start_id)
            ]
            impacted.sort(key=lambda r: (self._get_row(r["id"])["date_ecriture"], r["id"]))
            self._last = impacted
            return

        if q.startswith("update ecritures_caisse set solde = %s where id = %s"):
            solde, row_id = params
            row = self._get_row(row_id)
            row["solde"] = float(solde)
            self._last = None
            return

        raise AssertionError(f"Requête inattendue dans FakeCursor: {query}")

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []

    def _get_row(self, row_id):
        for r in self.rows:
            if r["id"] == row_id:
                return r
        raise AssertionError(f"id introuvable: {row_id}")


class TestSaisieCaisseIncremental(unittest.TestCase):
    def test_is_position_before(self):
        self.assertTrue(_is_position_before(date(2026, 1, 1), 1, date(2026, 1, 2), 1))
        self.assertFalse(_is_position_before(date(2026, 1, 3), 1, date(2026, 1, 2), 99))
        self.assertTrue(_is_position_before(date(2026, 1, 2), 5, date(2026, 1, 2), 6))
        self.assertFalse(_is_position_before(date(2026, 1, 2), 6, date(2026, 1, 2), 5))

    def test_get_update_recalc_pivot(self):
        # Déplacement vers plus tard -> pivot = ancienne position
        pivot = get_update_recalc_pivot(date(2026, 1, 2), 10, date(2026, 1, 5), 10)
        self.assertEqual(pivot, (date(2026, 1, 2), 10))

        # Déplacement vers plus tôt -> pivot = nouvelle position
        pivot = get_update_recalc_pivot(date(2026, 1, 5), 10, date(2026, 1, 2), 10)
        self.assertEqual(pivot, (date(2026, 1, 2), 10))

    def test_recalculate_from_insertion_in_past(self):
        rows = [
            {"id": 1, "date_ecriture": date(2026, 1, 1), "debit": 100.0, "credit": 0.0, "solde": 100.0},
            # nouvelle écriture insérée dans le passé (solde initialement faux)
            {"id": 3, "date_ecriture": date(2026, 1, 5), "debit": 10.0, "credit": 0.0, "solde": 0.0},
            # ancienne écriture dont le solde doit être décalé
            {"id": 2, "date_ecriture": date(2026, 1, 10), "debit": 0.0, "credit": 20.0, "solde": 80.0},
        ]
        cursor = FakeCursor(rows)

        recalculate_soldes_from(cursor, date(2026, 1, 5), 3)

        self.assertEqual(cursor._get_row(1)["solde"], 100.0)
        self.assertEqual(cursor._get_row(3)["solde"], 110.0)
        self.assertEqual(cursor._get_row(2)["solde"], 90.0)

    def test_recalculate_from_deletion(self):
        # Cas après suppression d'une écriture au 2026-01-02 id=2
        rows = [
            {"id": 1, "date_ecriture": date(2026, 1, 1), "debit": 100.0, "credit": 0.0, "solde": 100.0},
            # solde stale: devrait devenir 150 après suppression de -20
            {"id": 3, "date_ecriture": date(2026, 1, 3), "debit": 50.0, "credit": 0.0, "solde": 130.0},
        ]
        cursor = FakeCursor(rows)

        recalculate_soldes_from(cursor, date(2026, 1, 2), 2)

        self.assertEqual(cursor._get_row(1)["solde"], 100.0)
        self.assertEqual(cursor._get_row(3)["solde"], 150.0)

    def test_recalculate_after_update_move_later(self):
        # id=2 déplacée du 2026-01-02 vers 2026-01-04
        # Après update (avant recalcul), les soldes sont encore ceux de l'ancien ordre.
        rows = [
            {"id": 1, "date_ecriture": date(2026, 1, 1), "debit": 100.0, "credit": 0.0, "solde": 100.0},
            # devrait passer à 150 (car id=2 n'est plus avant)
            {"id": 3, "date_ecriture": date(2026, 1, 3), "debit": 50.0, "credit": 0.0, "solde": 130.0},
            # devrait devenir 130 en fin de séquence
            {"id": 2, "date_ecriture": date(2026, 1, 4), "debit": 0.0, "credit": 20.0, "solde": 80.0},
        ]
        cursor = FakeCursor(rows)

        pivot_date, pivot_id = get_update_recalc_pivot(
            old_date=date(2026, 1, 2),
            old_id=2,
            new_date=date(2026, 1, 4),
            new_id=2,
        )
        self.assertEqual((pivot_date, pivot_id), (date(2026, 1, 2), 2))

        recalculate_soldes_from(cursor, pivot_date, pivot_id)

        self.assertEqual(cursor._get_row(1)["solde"], 100.0)
        self.assertEqual(cursor._get_row(3)["solde"], 150.0)
        self.assertEqual(cursor._get_row(2)["solde"], 130.0)

    def test_recalculate_after_update_move_earlier(self):
        # id=2 déplacée du 2026-01-04 vers 2026-01-02
        # Après update (avant recalcul), les soldes sont encore ceux de l'ancien ordre.
        rows = [
            {"id": 1, "date_ecriture": date(2026, 1, 1), "debit": 100.0, "credit": 0.0, "solde": 100.0},
            # devrait devenir 80 juste après id=1
            {"id": 2, "date_ecriture": date(2026, 1, 2), "debit": 0.0, "credit": 20.0, "solde": 130.0},
            # devrait revenir à 130 après id=2
            {"id": 3, "date_ecriture": date(2026, 1, 3), "debit": 50.0, "credit": 0.0, "solde": 150.0},
        ]
        cursor = FakeCursor(rows)

        pivot_date, pivot_id = get_update_recalc_pivot(
            old_date=date(2026, 1, 4),
            old_id=2,
            new_date=date(2026, 1, 2),
            new_id=2,
        )
        self.assertEqual((pivot_date, pivot_id), (date(2026, 1, 2), 2))

        recalculate_soldes_from(cursor, pivot_date, pivot_id)

        self.assertEqual(cursor._get_row(1)["solde"], 100.0)
        self.assertEqual(cursor._get_row(2)["solde"], 80.0)
        self.assertEqual(cursor._get_row(3)["solde"], 130.0)


if __name__ == "__main__":
    unittest.main()
