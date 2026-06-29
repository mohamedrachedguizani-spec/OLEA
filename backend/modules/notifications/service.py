"""
Service de notifications temps réel pour OLEA.

Modules couverts :
  - sage_bfc : mois_manquant, alertes_globales, nouveau_mois
  - forecast : depassement_budget, cycle_declenchable

Filtrage par permissions : chaque utilisateur ne reçoit que les notifications
des modules auxquels il a accès (table user_permissions).
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from database import db


SUPERADMIN_ALLOWED_MODULES = {"dashboard", "users", "audit", "admin"}


def init_notifications_tables():
    """Créer la table notifications si elle n'existe pas."""
    with db.get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                type VARCHAR(128) NOT NULL,
                module VARCHAR(64) NOT NULL,
                severity ENUM('critical', 'warning', 'info', 'success') NOT NULL DEFAULT 'info',
                title VARCHAR(512) NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                metadata JSON NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_notifications_user (user_id, is_read, created_at),
                INDEX idx_notifications_module (module),
                INDEX idx_notifications_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)


def purge_old_notifications(days: int = 30):
    """Supprimer les notifications de plus de N jours."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM notifications WHERE created_at < NOW() - INTERVAL %s DAY",
            (days,),
        )
        return cursor.rowcount


def _get_users_for_module(module_name: str) -> List[int]:
    """
    Retourne les user_ids ayant can_read=TRUE sur un module donné.
    Exclut les superadmins (ils ont leur propre canal admin).
    """
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT up.user_id FROM user_permissions up "
            "JOIN users u ON u.id = up.user_id "
            "WHERE up.module_name = %s AND up.can_read = TRUE "
            "AND u.is_active = TRUE AND u.role != 'superadmin'",
            (module_name,),
        )
        return [row["user_id"] for row in cursor.fetchall()]


def _get_superadmin_ids() -> List[int]:
    """Retourne les user_ids des superadmins actifs."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE role = 'superadmin' AND is_active = TRUE"
        )
        return [row["id"] for row in cursor.fetchall()]


def create_notification(
    user_ids: List[int],
    notif_type: str,
    module: str,
    severity: str,
    title: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
    dedup_minutes: int = 10,
) -> List[int]:
    """
    Crée une notification pour chaque user_id et pousse via WebSocket.
    Retourne la liste des IDs de notifications créées.

    dedup_minutes: si > 0, ignore la création si une notification identique
    (même user_id, type, module) existe déjà dans les N dernières minutes.
    """
    if not user_ids:
        return []

    from ws_manager import manager

    meta_json = json.dumps(metadata, default=str) if metadata else None
    created_ids = []

    with db.get_cursor() as cursor:
        for uid in user_ids:
            # 1. Déduplication par temps (évite le spam à très court terme)
            if dedup_minutes > 0:
                cursor.execute(
                    "SELECT id FROM notifications "
                    "WHERE user_id = %s AND type = %s AND module = %s "
                    "AND created_at >= NOW() - INTERVAL %s MINUTE "
                    "LIMIT 1",
                    (uid, notif_type, module, dedup_minutes),
                )
                if cursor.fetchone():
                    continue  # Notification identique récente, on skip

            # 2. Nettoyage de l'ancienne notification non lue du même type/module pour cet utilisateur
            cursor.execute(
                "SELECT id FROM notifications "
                "WHERE user_id = %s AND type = %s AND module = %s AND is_read = FALSE "
                "LIMIT 1",
                (uid, notif_type, module),
            )
            old_notif = cursor.fetchone()
            if old_notif:
                old_id = old_notif["id"]
                cursor.execute("DELETE FROM notifications WHERE id = %s", (old_id,))
                # Pousser la suppression de l'ancien élément via WebSocket
                manager.send_to_user(uid, "notifications", "delete", {"id": old_id})

            # 3. Insertion de la nouvelle notification
            cursor.execute(
                "INSERT INTO notifications (user_id, type, module, severity, title, message, metadata) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (uid, notif_type, module, severity, title, message, meta_json),
            )
            notif_id = cursor.lastrowid
            created_ids.append(notif_id)

            # Push temps réel via WebSocket de la nouvelle notification
            manager.send_to_user(uid, "notifications", "new", {
                "id": notif_id,
                "type": notif_type,
                "module": module,
                "severity": severity,
                "title": title,
                "message": message,
                "metadata": metadata,
                "is_read": False,
                "created_at": datetime.now().isoformat(),
            })

    return created_ids


def notify_module_users(
    module_name: str,
    notif_type: str,
    severity: str,
    title: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """Notifie tous les utilisateurs ayant accès à un module."""
    user_ids = _get_users_for_module(module_name)
    return create_notification(user_ids, notif_type, module_name, severity, title, message, metadata)


def notify_admins(
    notif_type: str,
    severity: str,
    title: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """Notifie tous les superadmins."""
    user_ids = _get_superadmin_ids()
    return create_notification(user_ids, notif_type, "admin", severity, title, message, metadata)


def get_user_notifications(
    user_id: int,
    user_role: str,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
) -> Dict[str, Any]:
    """
    Récupère les notifications d'un utilisateur filtrées par ses permissions module.
    """
    with db.get_cursor() as cursor:
        # Déterminer les modules autorisés
        if user_role == "superadmin":
            allowed_modules = list(SUPERADMIN_ALLOWED_MODULES)
        else:
            cursor.execute(
                "SELECT module_name FROM user_permissions "
                "WHERE user_id = %s AND can_read = TRUE",
                (user_id,),
            )
            allowed_modules = [row["module_name"] for row in cursor.fetchall()]

        if not allowed_modules:
            return {"items": [], "total": 0, "unread": 0}

        placeholders = ", ".join(["%s"] * len(allowed_modules))

        # Filtre unread
        read_filter = " AND is_read = FALSE" if unread_only else ""

        # Total
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM notifications "
            f"WHERE user_id = %s AND module IN ({placeholders}){read_filter}",
            [user_id] + allowed_modules,
        )
        total = cursor.fetchone()["cnt"]

        # Unread count
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM notifications "
            f"WHERE user_id = %s AND module IN ({placeholders}) AND is_read = FALSE",
            [user_id] + allowed_modules,
        )
        unread = cursor.fetchone()["cnt"]

        # Items
        cursor.execute(
            f"SELECT id, user_id, type, module, severity, title, message, is_read, metadata, created_at "
            f"FROM notifications "
            f"WHERE user_id = %s AND module IN ({placeholders}){read_filter} "
            f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
            [user_id] + allowed_modules + [limit, offset],
        )
        rows = cursor.fetchall()

        items = []
        for row in rows:
            meta = row.get("metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = None
            items.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "type": row["type"],
                "module": row["module"],
                "severity": row["severity"],
                "title": row["title"],
                "message": row["message"],
                "is_read": bool(row["is_read"]),
                "metadata": meta,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            })

        return {"items": items, "total": total, "unread": unread}


def get_unread_count(user_id: int, user_role: str) -> int:
    """Compteur de notifications non lues pour un utilisateur."""
    with db.get_cursor() as cursor:
        if user_role == "superadmin":
            allowed_modules = list(SUPERADMIN_ALLOWED_MODULES)
        else:
            cursor.execute(
                "SELECT module_name FROM user_permissions "
                "WHERE user_id = %s AND can_read = TRUE",
                (user_id,),
            )
            allowed_modules = [row["module_name"] for row in cursor.fetchall()]

        if not allowed_modules:
            return 0

        placeholders = ", ".join(["%s"] * len(allowed_modules))
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM notifications "
            f"WHERE user_id = %s AND module IN ({placeholders}) AND is_read = FALSE",
            [user_id] + allowed_modules,
        )
        return cursor.fetchone()["cnt"]


def mark_as_read(notification_id: int, user_id: int) -> bool:
    """Marquer une notification comme lue."""
    ok = False
    with db.get_cursor() as cursor:
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s",
            (notification_id, user_id),
        )
        ok = cursor.rowcount > 0

    if ok:
        from ws_manager import manager
        manager.send_to_user(user_id, "notifications", "read", {"id": notification_id})
    return ok


def mark_all_read(user_id: int, user_role: str) -> int:
    """Marquer toutes les notifications comme lues."""
    count = 0
    with db.get_cursor() as cursor:
        if user_role == "superadmin":
            allowed_modules = list(SUPERADMIN_ALLOWED_MODULES)
        else:
            cursor.execute(
                "SELECT module_name FROM user_permissions "
                "WHERE user_id = %s AND can_read = TRUE",
                (user_id,),
            )
            allowed_modules = [row["module_name"] for row in cursor.fetchall()]

        if not allowed_modules:
            return 0

        placeholders = ", ".join(["%s"] * len(allowed_modules))
        cursor.execute(
            f"UPDATE notifications SET is_read = TRUE "
            f"WHERE user_id = %s AND module IN ({placeholders}) AND is_read = FALSE",
            [user_id] + allowed_modules,
        )
        count = cursor.rowcount

    if count > 0:
        from ws_manager import manager
        manager.send_to_user(user_id, "notifications", "read_all", {})
    return count


def delete_notification(notification_id: int, user_id: int) -> bool:
    """Supprimer une notification."""
    ok = False
    with db.get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM notifications WHERE id = %s AND user_id = %s",
            (notification_id, user_id),
        )
        ok = cursor.rowcount > 0

    if ok:
        from ws_manager import manager
        manager.send_to_user(user_id, "notifications", "delete", {"id": notification_id})
    return ok
