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