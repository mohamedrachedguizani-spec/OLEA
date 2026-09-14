import asyncio
import importlib
import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from fastapi import HTTPException


sage_router = importlib.import_module("modules.sage_bfc.router")


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.query = ""
        self.params = ()

    def execute(self, query, params=()):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class TestSageBfcMonthlyFilters(unittest.TestCase):
    def _cursor_context(self, cursor):
        @contextmanager
        def context():
            yield cursor
        return context

    def test_year_filter_uses_an_index_friendly_date_range(self):
        cursor = FakeCursor()
        with patch.object(sage_router.db, "get_cursor", self._cursor_context(cursor)):
            result = asyncio.run(sage_router.get_all_monthly(year=2026, periode=None))
        self.assertEqual(result, [])
        self.assertIn("periode >= %s AND periode < %s", cursor.query)
        self.assertEqual(cursor.params, (date(2026, 1, 1), date(2027, 1, 1)))

    def test_period_filter_is_applied_server_side(self):
        cursor = FakeCursor()
        with patch.object(sage_router.db, "get_cursor", self._cursor_context(cursor)):
            asyncio.run(sage_router.get_all_monthly(year=None, periode="2026-06"))
        self.assertIn("periode = %s", cursor.query)
        self.assertEqual(cursor.params, (date(2026, 6, 1),))

    def test_rejects_a_period_outside_the_requested_year(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(sage_router.get_all_monthly(year=2027, periode="2026-06"))
        self.assertEqual(raised.exception.status_code, 400)

    def test_monthly_years_are_lightweight_and_include_counts(self):
        cursor = FakeCursor([
            {"year": 2027, "months_count": 1},
            {"year": 2026, "months_count": 12},
        ])
        with patch.object(sage_router.db, "get_cursor", self._cursor_context(cursor)):
            result = asyncio.run(sage_router.get_monthly_years())
        self.assertEqual(result["years"], [2027, 2026])
        self.assertEqual(result["items"][1], {"year": 2026, "months_count": 12})


if __name__ == "__main__":
    unittest.main()
