# modules/auth/__init__.py
"""
Module d'authentification et d'autorisation OLEA.

Tables créées automatiquement :
  - users : utilisateurs avec rôles (superadmin, comptable, financier, dirigeant)
  - user_permissions : droits d'accès par module et par action

Sécurité :
  - JWT access token (15 min) + refresh token (7 jours) en cookies httpOnly
  - Pas de stockage des tokens en base de données ni en localStorage
  - Révocation via token_version (sans blacklist)
  - Mot de passe hashé avec bcrypt
"""

from database import db
from .security import hash_password
from .router import router


def init_auth_tables():
    """
    Crée les tables d'authentification et insère le superadmin par défaut
    s'il n'existe pas encore.

    Superadmin par défaut :
      - username : admin
      - password : admin123
      - ⚠️  À changer dès la première connexion !
    """
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            # ─── Table users ───
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    full_name VARCHAR(100) NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    role ENUM('superadmin', 'comptable', 'financier', 'dirigeant') NOT NULL DEFAULT 'comptable',
                    is_active BOOLEAN DEFAULT TRUE,
                    token_version INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ─── Table user_permissions ───
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    module_name VARCHAR(50) NOT NULL,
                    can_read BOOLEAN DEFAULT FALSE,
                    can_write BOOLEAN DEFAULT FALSE,
                    can_delete BOOLEAN DEFAULT FALSE,
                    UNIQUE KEY unique_user_module (user_id, module_name),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # ─── Seed superadmin par défaut ───
            cursor.execute("SELECT id FROM users WHERE role = 'superadmin' LIMIT 1")
            if not cursor.fetchone():
                hashed = hash_password("admin123")
                cursor.execute(
                    "INSERT INTO users (username, email, full_name, hashed_password, role) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    ("admin", "admin@olea.local", "Super Administrateur", hashed, "superadmin"),
                )
                print("✅ Superadmin créé — username: admin / password: admin123")
                print("⚠️  Changez ce mot de passe dès la première connexion !")

            conn.commit()
            print("✅ Tables d'authentification initialisées")
