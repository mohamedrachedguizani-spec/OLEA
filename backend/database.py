# database.py
#
# Pool mysql-connector-python :
#   ─ pool_size     : connexions permanentes maintenues ouvertes
#   ─ REMARQUE      : max_overflow n'existe PAS dans mysql-connector-python,
#                     c'est un paramètre SQLAlchemy uniquement.
#                     Ici on dimensionne pool_size pour couvrir le pic de charge.
#   ─ Calcul pour 40 requêtes simultanées :
#       • Chaque requête tient une connexion ~1–5 ms (SELECT sur PRIMARY KEY)
#       • pool_size = 32 → largement suffisant (marge x2 sur le pic réel)
#       • connection_timeout = 5 s → erreur propre si le pool est saturé
#
# Attention async/sync :
#   FastAPI exécute les endpoints `async def` dans l'event loop :
#   un appel DB synchrone bloquant dans un `async def` GEL l'event loop entier.
#   → Les routes DB-intensive sont déclarées en `def` (synchrone) :
#     FastAPI les exécute automatiquement dans un thread pool (anyio).

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector.errors import PoolError
from contextlib import contextmanager
from fastapi import HTTPException, status
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Taille du pool : couvre 40 req simultanées avec marge
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "32"))
# Délai max (s) pour obtenir une connexion libre avant d'échouer
_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "5"))


class Database:
    def __init__(self):
        self.host     = os.getenv("DB_HOST",     "localhost")
        self.user     = os.getenv("DB_USER",     "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_NAME",     "gestion_caisse")
        self.port     = int(os.getenv("DB_PORT", 3306))
        self._pool: Optional[MySQLConnectionPool] = None

    def _get_pool(self) -> MySQLConnectionPool:
        """Initialise le pool de connexions (lazy, thread-safe au démarrage)."""
        if self._pool is None:
            self._pool = MySQLConnectionPool(
                pool_name="olea_pool",
                pool_size=_POOL_SIZE,
                pool_reset_session=True,
                connection_timeout=_POOL_TIMEOUT,
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                charset="utf8mb4",
                collation="utf8mb4_unicode_ci",
            )
            print(f"✅ Pool DB initialisé — pool_size={_POOL_SIZE}, timeout={_POOL_TIMEOUT}s")
        return self._pool

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = self._get_pool().get_connection()
            yield conn
        except PoolError:
            # Pool épuisé (pic > pool_size requêtes simultanées)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Serveur surchargé — réessayez dans quelques secondes",
            )
        except Error as e:
            print(f"Erreur DB : {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Erreur de connexion à la base de données",
            )
        finally:
            if conn and conn.is_connected():
                conn.close()  # Retourne la connexion au pool (non fermée réellement)

    @contextmanager
    def get_cursor(self, connection=None):
        if connection:
            cursor = connection.cursor(dictionary=True)
            try:
                yield cursor
            finally:
                cursor.close()
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                try:
                    yield cursor
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
                finally:
                    cursor.close()

db = Database()


def init_sage_bfc_tables():
    """Créer la table sage_bfc_monthly si elle n'existe pas"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sage_bfc_monthly (
                id INT AUTO_INCREMENT PRIMARY KEY,
                periode DATE NOT NULL UNIQUE,
                resume JSON NOT NULL,
                lignes LONGTEXT NOT NULL,
                validations JSON,
                alertes_globales JSON,
                file_name VARCHAR(255),
                lignes_count INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Stockage des valeurs cumulées brutes (pour calcul du réel mensuel = cumulé M - cumulé M-1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sage_bfc_monthly_cumule (
                id INT AUTO_INCREMENT PRIMARY KEY,
                periode DATE NOT NULL UNIQUE,
                resume JSON NOT NULL,
                lignes LONGTEXT NOT NULL,
                file_name VARCHAR(255),
                lignes_count INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)


def init_forecast_tables():
    """Créer les tables de prévision BFC"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bfc_budget_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                year INT NOT NULL,
                month TINYINT NOT NULL,
                agregat_key VARCHAR(64) NOT NULL,
                agregat_label VARCHAR(255) NOT NULL,
                value DOUBLE NOT NULL DEFAULT 0,
                source_file VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_bfc_budget_history (year, month, agregat_key),
                INDEX idx_bfc_budget_history_year_month (year, month),
                INDEX idx_bfc_budget_history_agregat (agregat_key)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bfc_forecast_runs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                forecast_year INT NOT NULL,
                cycle_code VARCHAR(32) NOT NULL,
                cycle_month TINYINT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'done',
                metadata JSON NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_bfc_forecast_runs_year_cycle (forecast_year, cycle_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bfc_forecast_values (
                id INT AUTO_INCREMENT PRIMARY KEY,
                run_id INT NOT NULL,
                forecast_year INT NOT NULL,
                cycle_code VARCHAR(32) NOT NULL,
                agregat_key VARCHAR(64) NOT NULL,
                agregat_label VARCHAR(255) NOT NULL,
                nature VARCHAR(32) NOT NULL,
                is_derived BOOLEAN NOT NULL DEFAULT FALSE,
                month TINYINT NOT NULL,
                forecast_value DOUBLE NOT NULL DEFAULT 0,
                lower_value DOUBLE NULL,
                upper_value DOUBLE NULL,
                actual_value DOUBLE NULL,
                ecart_value DOUBLE NULL,
                ecart_pct DOUBLE NULL,
                alert_level VARCHAR(32) NULL,
                model_name VARCHAR(64) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_bfc_forecast_values (forecast_year, cycle_code, agregat_key, month),
                INDEX idx_bfc_forecast_values_lookup (forecast_year, cycle_code, month),
                CONSTRAINT fk_bfc_forecast_values_run
                    FOREIGN KEY (run_id) REFERENCES bfc_forecast_runs(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bfc_forecast_manual_subvalues (
                id INT AUTO_INCREMENT PRIMARY KEY,
                forecast_year INT NOT NULL,
                cycle_code VARCHAR(32) NOT NULL,
                agregat_key VARCHAR(64) NOT NULL,
                month TINYINT NOT NULL,
                subagregat_key VARCHAR(128) NOT NULL,
                subagregat_label VARCHAR(255) NOT NULL,
                forecast_value DOUBLE NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_bfc_forecast_manual_subvalues (forecast_year, cycle_code, agregat_key, month, subagregat_key),
                INDEX idx_bfc_forecast_manual_subvalues_lookup (forecast_year, cycle_code, agregat_key, month)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)