from database import db
from .router import router


def init_audit_tables():
    """Crée la table d'audit si elle n'existe pas."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NULL,
                username VARCHAR(128) NULL,
                action VARCHAR(64) NOT NULL,
                module VARCHAR(64) NOT NULL,
                entity_type VARCHAR(64) NULL,
                entity_id VARCHAR(128) NULL,
                detail JSON NULL,
                ip_address VARCHAR(64) NULL,
                user_agent VARCHAR(255) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_audit_logs_created_at (created_at),
                INDEX idx_audit_logs_user (user_id),
                INDEX idx_audit_logs_module (module),
                INDEX idx_audit_logs_action (action)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


__all__ = ["router", "init_audit_tables"]
