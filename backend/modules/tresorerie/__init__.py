# modules/tresorerie/__init__.py
from database import db
from .router import router


def init_tresorerie_tables():
    """Crée les tables du module Trésorerie."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tresorerie_imports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                compte_banque VARCHAR(32) NOT NULL,
                periode_debut DATE NULL,
                periode_fin DATE NULL,
                file_name VARCHAR(255) NOT NULL,
                file_type VARCHAR(32) NOT NULL,
                taux_conversion DOUBLE NULL DEFAULT NULL,
                devise_source VARCHAR(8) NULL DEFAULT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'extracted',
                created_by_user_id INT NULL DEFAULT NULL,
                created_by_username VARCHAR(64) NULL DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_treso_import_compte (compte_banque),
                INDEX idx_treso_import_periode (periode_debut, periode_fin),
                INDEX idx_treso_import_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tresorerie_movements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                import_id INT NOT NULL,
                date_operation DATE NOT NULL,
                reference VARCHAR(64) NULL,
                libelle VARCHAR(255) NOT NULL,
                debit DOUBLE NOT NULL DEFAULT 0,
                credit DOUBLE NOT NULL DEFAULT 0,
                nature VARCHAR(24) NULL DEFAULT NULL,
                nature_suggeree VARCHAR(24) NULL DEFAULT NULL,
                classified_by_user_id INT NULL DEFAULT NULL,
                classified_by_username VARCHAR(64) NULL DEFAULT NULL,
                classified_at DATETIME NULL DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_treso_mov_import (import_id),
                INDEX idx_treso_mov_date (date_operation),
                INDEX idx_treso_mov_nature (nature),
                CONSTRAINT fk_treso_mov_import
                    FOREIGN KEY (import_id) REFERENCES tresorerie_imports(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


__all__ = ["router", "init_tresorerie_tables"]
