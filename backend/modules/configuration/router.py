from fastapi import APIRouter, Depends, HTTPException
from typing import List

from database import db
from modules.auth.dependencies import get_current_user, require_permission
from .models import CompteConfiguration, CompteConfigurationCreate


router = APIRouter(
    tags=["Configuration"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(get_current_user)],
)


@router.get("/configuration/comptes/", response_model=List[CompteConfiguration])
def get_configuration_comptes(
    search: str = "",
    limit: int = 200,
    user: dict = Depends(require_permission("configuration", "read")),
):
    """Lister les comptes configurés (code + libellé)."""
    safe_limit = max(1, min(limit, 500))
    with db.get_cursor() as cursor:
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
            LIMIT %s
            """,
            (f"%{search}%", f"%{search}%", safe_limit),
        )
        return cursor.fetchall()


@router.post("/configuration/comptes/", response_model=CompteConfiguration)
def create_or_update_compte(
    payload: CompteConfigurationCreate,
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

    return created_or_updated
