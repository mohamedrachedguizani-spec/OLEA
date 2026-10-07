from database import db
from .catalog import PERMISSIONS, PROFILES


DEFAULT_PROFILE_BY_USER_ROLE = {
    "superadmin": "SUPER_ADMIN",
    "financier": "FINANCIER",
    "dirigeant": "DIRIGEANT",
    "consultant": "CONSULTANT",
    "comptable": "COMPTABLE",
}

CAISSE_LEGACY_MANAGE_PERMISSIONS = (
    "saisie_caisse.create",
    "saisie_caisse.update",
    "saisie_caisse.delete",
    "saisie_caisse.migrate",
)
CAISSE_MANAGE_PERMISSION = "saisie_caisse.crud_ecriture_caisse_manage"

SAGE_BFC_PERMISSION_REPLACEMENTS = {
    "sage_bfc.export_excel": "sage_bfc.read",
    "sage_bfc.audit.read": "sage_bfc.read",
    "sage_bfc.recompute": "sage_bfc.import",
}

# Permissions à propager aux profils existants lors d'une montée de version
NEW_PROFILE_PERMISSIONS = {
    "COMPTABLE": {"balance_agee.generate", "balance_agee.read", "balance_agee.export_pdf", "balance_agee.print",
                 "balance_fournisseur.generate", "balance_fournisseur.read", "balance_fournisseur.export_pdf",
                 "balance_fournisseur.print", "balance_agee.delete", "balance_fournisseur.delete"},
    "FINANCIER": {"balance_agee.generate", "balance_agee.read", "balance_agee.export_pdf", "balance_agee.print",
                 "balance_fournisseur.generate", "balance_fournisseur.read", "balance_fournisseur.export_pdf",
                 "balance_fournisseur.print", "balance_agee.delete", "balance_fournisseur.delete"},
}

# « balance_*.read » permettait jusqu'ici de GÉNÉRER la balance. Il devient « consultation » et le droit de génération
# passe dans « balance_*.generate » : à la première création de ce droit, tous les profils qui avaient « read » le reçoivent
# (comportement inchangé pour eux). Les profils créés ensuite en « consultation seule » ne le reçoivent pas.
BALANCE_GENERATE_MIGRATION = {
    "balance_agee.generate": "balance_agee.read",
    "balance_fournisseur.generate": "balance_fournisseur.read",
}


def init_access_tables():
    """Crée et alimente le catalogue RBAC sans supprimer les droits existants."""
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_permissions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    code VARCHAR(120) NOT NULL UNIQUE,
                    name VARCHAR(180) NOT NULL,
                    module VARCHAR(80) NOT NULL,
                    description VARCHAR(500) NULL,
                    INDEX idx_access_permissions_module (module)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_roles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    code VARCHAR(80) NOT NULL UNIQUE,
                    name VARCHAR(120) NOT NULL,
                    description VARCHAR(500) NULL,
                    is_system BOOLEAN NOT NULL DEFAULT TRUE,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS access_role_permissions (
                    role_id INT NOT NULL,
                    permission_id INT NOT NULL,
                    PRIMARY KEY (role_id, permission_id),
                    FOREIGN KEY (role_id) REFERENCES access_roles(id) ON DELETE CASCADE,
                    FOREIGN KEY (permission_id) REFERENCES access_permissions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_access_roles (
                    user_id INT NOT NULL PRIMARY KEY,
                    role_id INT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (role_id) REFERENCES access_roles(id) ON DELETE RESTRICT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            cursor.execute("SELECT code FROM access_permissions")
            existing_before = {row["code"] for row in cursor.fetchall()}   # pour ne propager un nouveau droit qu'une seule fois

            for code, (name, module) in PERMISSIONS.items():
                cursor.execute(
                    "INSERT INTO access_permissions (code, name, module) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE name = VALUES(name), module = VALUES(module)",
                    (code, name, module),
                )

            _consolidate_caisse_manage_permission(cursor)
            _consolidate_sage_bfc_permissions(cursor)
            _propagate_new_permissions(cursor, existing_before)
            _migrate_balance_generate_permissions(cursor, existing_before)

            for code, (name, description, permission_codes) in PROFILES.items():
                cursor.execute(
                    "INSERT IGNORE INTO access_roles (code, name, description, is_system) VALUES (%s, %s, %s, TRUE)",
                    (code, name, description),
                )
                is_new_profile = cursor.rowcount == 1
                cursor.execute(
                    "UPDATE access_roles SET name = %s, description = %s WHERE code = %s",
                    (name, description, code),
                )
                cursor.execute("SELECT id FROM access_roles WHERE code = %s", (code,))
                role_id = cursor.fetchone()["id"]
                if is_new_profile:
                    for permission_code in permission_codes:
                        cursor.execute(
                            "INSERT IGNORE INTO access_role_permissions (role_id, permission_id) "
                            "SELECT %s, id FROM access_permissions WHERE code = %s",
                            (role_id, permission_code),
                        )

            _assign_unassigned_users(cursor)
            conn.commit()


def _profile_code_for_user(user_role: str) -> str:
    return DEFAULT_PROFILE_BY_USER_ROLE.get(user_role, "COMPTABLE")


def _propagate_new_permissions(cursor, existing_before=frozenset()):
    """Ajoute les NOUVELLES permissions aux profils existants, une seule fois (au moment où le droit est créé).
    Un droit déjà présent n'est jamais réattribué : un administrateur peut donc le retirer d'un profil durablement."""
    for profile_code, permission_codes in NEW_PROFILE_PERMISSIONS.items():
        cursor.execute("SELECT id FROM access_roles WHERE code = %s", (profile_code,))
        row = cursor.fetchone()
        if not row:
            continue
        role_id = row["id"]
        for perm_code in permission_codes:
            if perm_code in existing_before:
                continue
            cursor.execute(
                "INSERT IGNORE INTO access_role_permissions (role_id, permission_id) "
                "SELECT %s, id FROM access_permissions WHERE code = %s",
                (role_id, perm_code),
            )


def _migrate_balance_generate_permissions(cursor, existing_before=frozenset()):
    """Donne « générer » à tous les profils qui avaient « balance_*.read » (une seule fois, à la création du droit)."""
    for new_code, old_code in BALANCE_GENERATE_MIGRATION.items():
        if new_code in existing_before:
            continue
        cursor.execute(
            "INSERT IGNORE INTO access_role_permissions (role_id, permission_id) "
            "SELECT rp.role_id, target.id FROM access_role_permissions rp "
            "JOIN access_permissions legacy ON legacy.id = rp.permission_id "
            "JOIN access_permissions target ON target.code = %s "
            "WHERE legacy.code = %s",
            (new_code, old_code),
        )


def _consolidate_caisse_manage_permission(cursor):
    """Remplace les quatre anciens droits de mutation par le droit CRUD unique."""
    placeholders = ",".join(["%s"] * len(CAISSE_LEGACY_MANAGE_PERMISSIONS))
    cursor.execute(
        "INSERT IGNORE INTO access_role_permissions (role_id, permission_id) "
        "SELECT DISTINCT rp.role_id, target.id "
        "FROM access_role_permissions rp "
        "JOIN access_permissions legacy ON legacy.id = rp.permission_id "
        "JOIN access_permissions target ON target.code = %s "
        f"WHERE legacy.code IN ({placeholders})",
        (CAISSE_MANAGE_PERMISSION, *CAISSE_LEGACY_MANAGE_PERMISSIONS),
    )
    cursor.execute(
        f"DELETE FROM access_permissions WHERE code IN ({placeholders})",
        CAISSE_LEGACY_MANAGE_PERMISSIONS,
    )


def _consolidate_sage_bfc_permissions(cursor):
    """Ramène les anciens droits SAGE → BFC aux quatre droits fonctionnels retenus."""
    for old_code, target_code in SAGE_BFC_PERMISSION_REPLACEMENTS.items():
        cursor.execute(
            "INSERT IGNORE INTO access_role_permissions (role_id, permission_id) "
            "SELECT rp.role_id, target.id FROM access_role_permissions rp "
            "JOIN access_permissions legacy ON legacy.id = rp.permission_id "
            "JOIN access_permissions target ON target.code = %s "
            "WHERE legacy.code = %s",
            (target_code, old_code),
        )
    placeholders = ",".join(["%s"] * len(SAGE_BFC_PERMISSION_REPLACEMENTS))
    cursor.execute(
        f"DELETE FROM access_permissions WHERE code IN ({placeholders})",
        tuple(SAGE_BFC_PERMISSION_REPLACEMENTS),
    )


def _assign_unassigned_users(cursor):
    """Affecte uniquement le profil standard correspondant au rôle utilisateur."""
    cursor.execute("""
        SELECT u.id, u.role
        FROM users u LEFT JOIN user_access_roles ur ON ur.user_id = u.id
        WHERE ur.user_id IS NULL
    """)
    for user in cursor.fetchall():
        role_code = _profile_code_for_user(user["role"])
        cursor.execute("SELECT id FROM access_roles WHERE code = %s", (role_code,))
        role_id = cursor.fetchone()["id"]
        cursor.execute(
            "INSERT IGNORE INTO user_access_roles (user_id, role_id) VALUES (%s, %s)",
            (user["id"], role_id),
        )


def get_user_permission_codes(cursor, user_id: int):
    cursor.execute("""
        SELECT p.code FROM user_access_roles ur
        JOIN access_roles r ON r.id = ur.role_id AND r.is_active = TRUE
        JOIN access_role_permissions rp ON rp.role_id = r.id
        JOIN access_permissions p ON p.id = rp.permission_id
        WHERE ur.user_id = %s ORDER BY p.code
    """, (user_id,))
    return [row["code"] for row in cursor.fetchall()]