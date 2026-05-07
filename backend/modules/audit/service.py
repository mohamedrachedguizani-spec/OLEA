import json
from typing import Optional, Dict, Any
from fastapi import Request
from database import db


def log_audit_action(
    *,
    user: Optional[dict],
    action: str,
    module: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Enregistre un événement d'audit (best-effort)."""
    try:
        from ws_manager import manager as ws_manager

        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        user_id = user.get("id") if user else None
        username = user.get("username") if user else None

        detail_payload = None
        if detail is not None:
            try:
                detail_payload = json.dumps(detail, ensure_ascii=False, default=str)
            except Exception:
                detail_payload = json.dumps({"detail": str(detail)}, ensure_ascii=False)

        with db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_logs (
                    user_id,
                    username,
                    action,
                    module,
                    entity_type,
                    entity_id,
                    detail,
                    ip_address,
                    user_agent
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    username,
                    action,
                    module,
                    entity_type,
                    entity_id,
                    detail_payload,
                    ip_address,
                    user_agent,
                ),
            )

        ws_manager.broadcast(
            "audit",
            "create",
            {"module": module, "action": action, "user": username, "entity_id": entity_id},
        )
    except Exception:
        return
