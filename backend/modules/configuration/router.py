from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user, require_permission
from modules.audit.service import log_audit_action
from .models import CompteConfiguration, CompteConfigurationCreate, CompteConfigurationUpdate, CompteConfigurationPage


router = APIRouter(
    tags=["Configuration"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(get_current_user)],
)


@router.get("/configuration/comptes/", response_model=CompteConfigurationPage)
def get_configuration_comptes(
    search: str = "",
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(require_permission("configuration", "read")),
):
    """Lister les comptes configurés (code + libellé)."""
    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), 200))
    offset = (safe_page - 1) * safe_page_size
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM (
                SELECT c.code_compte, c.libelle_compte
                FROM comptes c
                INNER JOIN (
                    SELECT code_compte, MAX(id) AS max_id
                    FROM comptes
                    GROUP BY code_compte
                ) x ON x.code_compte = c.code_compte AND x.max_id = c.id
                WHERE c.code_compte LIKE %s OR c.libelle_compte LIKE %s
            ) t
            """,
            (f"%{search}%", f"%{search}%"),
        )
        total = int(cursor.fetchone()["total"])
        pages = max(1, (total + safe_page_size - 1) // safe_page_size)

        if safe_page > pages:
            safe_page = pages
            offset = (safe_page - 1) * safe_page_size

        cursor.execute(
            """
            SELECT c.code_compte, c.libelle_compte
            FROM comptes c
            INNER JOIN (
                SELECT code_compte, MAX(id) AS max_id
                FROM comptes
                GROUP BY code_compte
            ) x ON x.code_compte = c.code_compte AND x.max_id = c.id
            WHERE c.code_compte LIKE %s OR c.libelle_compte LIKE %s
            ORDER BY c.code_compte
            LIMIT %s OFFSET %s
            """,
            (f"%{search}%", f"%{search}%", safe_page_size, offset),
        )
        items = cursor.fetchall()

    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "pages": pages,
    }


@router.post("/configuration/comptes/", response_model=CompteConfiguration)
def create_or_update_compte(
    payload: CompteConfigurationCreate,
    request: Request,
    user: dict = Depends(require_permission("configuration", "write")),
):
    """Créer un nouveau compte ou mettre à jour son libellé s'il existe."""
    code_compte = (payload.code_compte or "").strip()
    libelle_compte = (payload.libelle_compte or "").strip()

    if not code_compte:
        raise HTTPException(status_code=400, detail="Le code compte est obligatoire")
    if not libelle_compte:
        raise HTTPException(status_code=400, detail="Le libellé compte est obligatoire")

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM comptes
            WHERE code_compte = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (code_compte,),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE comptes
                SET libelle_compte = %s
                WHERE id = %s
                """,
                (libelle_compte, existing["id"]),
            )
        else:
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM comptes")
            next_id = int(cursor.fetchone()["next_id"])
            cursor.execute(
                """
                INSERT INTO comptes (id, code_compte, libelle_compte)
                VALUES (%s, %s, %s)
                """,
                (next_id, code_compte, libelle_compte),
            )

        cursor.execute(
            """
            SELECT code_compte, libelle_compte
            FROM comptes
            WHERE code_compte = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (code_compte,),
        )
        created_or_updated = cursor.fetchone()

    if not created_or_updated:
        raise HTTPException(status_code=500, detail="Impossible de sauvegarder le compte")

    ws_manager.broadcast(
        "configuration",
        "upsert",
        {"code_compte": created_or_updated["code_compte"]},
    )

    log_audit_action(
        user=user,
        action="upsert",
        module="configuration",
        entity_type="compte",
        entity_id=created_or_updated["code_compte"],
        detail={"libelle_compte": created_or_updated["libelle_compte"]},
        request=request,
    )

    return created_or_updated


@router.put("/configuration/comptes/{code_compte}", response_model=CompteConfiguration)
def update_compte(
    code_compte: str,
    payload: CompteConfigurationUpdate,
    request: Request,
    user: dict = Depends(require_permission("configuration", "write")),
):
    """Modifier le libellé ET le code d'un compte existant."""
    code = (code_compte or "").strip()
    new_code = (payload.code_compte or "").strip()
    libelle = (payload.libelle_compte or "").strip()

    if not code:
        raise HTTPException(status_code=400, detail="Le code compte est obligatoire")
    if not new_code:
        raise HTTPException(status_code=400, detail="Le nouveau code compte est obligatoire")
    if not libelle:
        raise HTTPException(status_code=400, detail="Le libellé compte est obligatoire")

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM comptes
            WHERE code_compte = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (code,),
        )
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Compte introuvable")

        cursor.execute(
            """
            UPDATE comptes
            SET code_compte = %s,
                libelle_compte = %s
            WHERE id = %s
            """,
            (new_code, libelle, existing["id"]),
        )

        cursor.execute(
            """
            SELECT code_compte, libelle_compte
            FROM comptes
            WHERE id = %s
            """,
            (existing["id"],),
        )
        updated = cursor.fetchone()

    if not updated:
        raise HTTPException(status_code=500, detail="Impossible de mettre à jour le compte")

    ws_manager.broadcast(
        "configuration",
        "update",
        {"code_compte": updated["code_compte"]},
    )

    log_audit_action(
        user=user,
        action="update",
        module="configuration",
        entity_type="compte",
        entity_id=updated["code_compte"],
        detail={"old_code": code, "libelle_compte": updated["libelle_compte"]},
        request=request,
    )

    return updated


@router.delete("/configuration/comptes/{code_compte}")
def delete_compte(
    code_compte: str,
    request: Request,
    user: dict = Depends(require_permission("configuration", "delete")),
):
    """Supprimer un compte (toutes les lignes avec ce code)."""
    code = (code_compte or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Le code compte est obligatoire")

    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM comptes WHERE code_compte = %s",
            (code,),
        )
        row = cursor.fetchone()
        if not row or row["cnt"] == 0:
            raise HTTPException(status_code=404, detail="Compte introuvable")

        cursor.execute(
            "DELETE FROM comptes WHERE code_compte = %s",
            (code,),
        )

    ws_manager.broadcast(
        "configuration",
        "delete",
        {"code_compte": code},
    )

    log_audit_action(
        user=user,
        action="delete",
        module="configuration",
        entity_type="compte",
        entity_id=code,
        request=request,
    )

    return {"message": "Compte supprimé avec succès", "code_compte": code}
