from database import db
from .router import router


def init_balance_tables():
    """Crée la table d'historique des balances âgées (clients et fournisseurs)."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS balance_agee_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                kind VARCHAR(16) NOT NULL,
                date_reference DATE NOT NULL,
                file_name VARCHAR(255) NULL,
                nb_tiers INT NOT NULL DEFAULT 0,
                montant_principal DECIMAL(18,3) NOT NULL DEFAULT 0,
                montant_contre DECIMAL(18,3) NOT NULL DEFAULT 0,
                montant_net DECIMAL(18,3) NOT NULL DEFAULT 0,
                montant_plus_90 DECIMAL(18,3) NOT NULL DEFAULT 0,
                controle_statut VARCHAR(16) NULL,
                result_json LONGTEXT NOT NULL,
                created_by_user_id INT NULL DEFAULT NULL,
                created_by_username VARCHAR(64) NULL DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_balance_agee_kind_created (kind, created_at),
                INDEX idx_balance_agee_kind_date (kind, date_reference)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


__all__ = ["router", "init_balance_tables"]