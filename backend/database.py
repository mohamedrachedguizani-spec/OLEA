# database.py
import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_NAME", "gestion_caisse")
        self.port = os.getenv("DB_PORT", 3306)
    
    @contextmanager
    def get_connection(self):
        connection = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port
            )
            yield connection
        except Error as e:
            print(f"Erreur de connexion à la base de données: {e}")
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()
    
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