"""
Script one-shot: migrer l'historique budget 2024/2025 vers MySQL
Usage:
    python scripts/migrate_budgets_to_db.py
"""

from pathlib import Path

from database import init_forecast_tables
from modules.forecast.engine import import_historical_csv


def main():
    backend_root = Path(__file__).resolve().parents[1]
    files = [
        str(backend_root / "budget_2024_cloture.csv"),
        str(backend_root / "budget_2025_cloture.csv"),
    ]

    init_forecast_tables()
    rows_written, years = import_historical_csv(files)
    print(f"✅ Migration terminée: {rows_written} lignes upsert ({years})")


if __name__ == "__main__":
    main()
