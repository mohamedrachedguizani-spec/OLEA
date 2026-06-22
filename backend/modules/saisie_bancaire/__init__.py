from database import db
from .router import router


def init_saisie_bancaire_tables():
    """Crée les tables nécessaires au module Saisie Bancaire."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_reconciliation_batches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                periode_debut DATE NULL,
                periode_fin DATE NULL,
                compte_banque VARCHAR(32) NOT NULL,
                compte_comptable VARCHAR(32) NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_type VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'uploaded',
                taux_conversion DOUBLE NULL DEFAULT NULL,
                devise_source VARCHAR(8) NULL DEFAULT NULL,
                created_by_user_id INT NULL DEFAULT NULL,
                created_by_username VARCHAR(64) NULL DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_bank_reco_batch_compte (compte_banque),
                INDEX idx_bank_reco_batch_periode (periode_debut, periode_fin)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

        # --- Migration : ajouter les colonnes taux/devise si elles n'existent pas ---
        for col, col_def in [
            ("taux_conversion", "DOUBLE NULL DEFAULT NULL"),
            ("devise_source", "VARCHAR(8) NULL DEFAULT NULL"),
            ("created_by_user_id", "INT NULL DEFAULT NULL"),
            ("created_by_username", "VARCHAR(64) NULL DEFAULT NULL"),
        ]:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'bank_reconciliation_batches'
                  AND column_name = %s
                """,
                (col,),
            )
            if cursor.fetchone()["cnt"] == 0:
                cursor.execute(
                    f"ALTER TABLE bank_reconciliation_batches ADD COLUMN {col} {col_def}"
                )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_reconciliation_movements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                batch_id INT NOT NULL,
                date_operation DATE NOT NULL,
                reference VARCHAR(64) NULL,
                libelle VARCHAR(255) NOT NULL,
                debit DOUBLE NOT NULL DEFAULT 0,
                credit DOUBLE NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_bank_reco_mov_batch (batch_id),
                CONSTRAINT fk_bank_reco_mov_batch
                    FOREIGN KEY (batch_id) REFERENCES bank_reconciliation_batches(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_reconciliation_sage_lines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                batch_id INT NOT NULL,
                movement_id INT NOT NULL,
                line_no TINYINT NOT NULL,
                societe VARCHAR(8) NOT NULL,
                journal VARCHAR(16) NOT NULL,
                date_ecriture DATE NOT NULL,
                compte VARCHAR(32) NULL,
                tiers VARCHAR(64) NULL,
                debit DOUBLE NOT NULL DEFAULT 0,
                credit DOUBLE NOT NULL DEFAULT 0,
                section_analytique VARCHAR(64) NULL,
                numero_piece VARCHAR(64) NOT NULL,
                libelle VARCHAR(255) NOT NULL,
                devise VARCHAR(8) NOT NULL,
                type_piece VARCHAR(8) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_bank_reco_sage_batch (batch_id),
                INDEX idx_bank_reco_sage_mov (movement_id),
                CONSTRAINT fk_bank_reco_sage_batch
                    FOREIGN KEY (batch_id) REFERENCES bank_reconciliation_batches(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_bank_reco_sage_movement
                    FOREIGN KEY (movement_id) REFERENCES bank_reconciliation_movements(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_reconciliation_session_entries (
                id INT AUTO_INCREMENT PRIMARY KEY,
                batch_id INT NOT NULL,
                movement_id INT NOT NULL,
                compte VARCHAR(32) NULL,
                tiers VARCHAR(64) NULL,
                section_analytique VARCHAR(64) NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_session_batch_mov (batch_id, movement_id),
                INDEX idx_session_batch (batch_id),
                CONSTRAINT fk_session_batch
                    FOREIGN KEY (batch_id) REFERENCES bank_reconciliation_batches(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_session_movement
                    FOREIGN KEY (movement_id) REFERENCES bank_reconciliation_movements(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


__all__ = ["router", "init_saisie_bancaire_tables"]
