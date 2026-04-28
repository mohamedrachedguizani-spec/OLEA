from database import db
from .router import router


def init_configuration_tables():
    """Crée les tables nécessaires au module Configuration."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS comptes (
                id INT(11) NOT NULL,
                code_compte VARCHAR(20) NOT NULL,
                libelle_compte VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
            """
        )


__all__ = ["router", "init_configuration_tables"]
