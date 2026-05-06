from datetime import date
from typing import Optional

import json

from fastapi import APIRouter, Depends, Query

from database import db
from modules.auth.dependencies import get_current_user, require_role
from modules.auth.models import RoleEnum
from .models import AuditLogPage


router = APIRouter(
    tags=["Audit"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(get_current_user), Depends(require_role(RoleEnum.superadmin))],
)


@router.get("/audit/logs", response_model=AuditLogPage)
def list_audit_logs(
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    user_id: Optional[int] = Query(None),
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), 200))
    offset = (safe_page - 1) * safe_page_size

    filters = []
    params = []

    if user_id is not None:
        filters.append("user_id = %s")
        params.append(user_id)

    if module:
        filters.append("module = %s")
        params.append(module)

    if action:
        filters.append("action = %s")
        params.append(action)

    if date_from:
        filters.append("created_at >= %s")
        params.append(date_from)

    if date_to:
        filters.append("created_at <= %s")
        params.append(date_to)

    if search:
        filters.append(
            "(username LIKE %s OR module LIKE %s OR action LIKE %s OR entity_type LIKE %s OR entity_id LIKE %s)"
        )
        like = f"%{search}%"
        params.extend([like, like, like, like, like])

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM audit_logs {where_clause}",
            tuple(params),
        )
        total = int(cursor.fetchone()["total"])
        pages = max(1, (total + safe_page_size - 1) // safe_page_size)

        if safe_page > pages:
            safe_page = pages
            offset = (safe_page - 1) * safe_page_size

        cursor.execute(
            f"""
            SELECT id, user_id, username, action, module, entity_type, entity_id,
                   detail, ip_address, user_agent, created_at
            FROM audit_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [safe_page_size, offset]),
        )
        items = cursor.fetchall()

    for item in items:
        detail = item.get("detail")
        if isinstance(detail, str):
            try:
                item["detail"] = json.loads(detail)
            except Exception:
                item["detail"] = {"raw": detail}

    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "pages": pages,
    }
