# modules/saisie_caisse/router.py
from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import date, datetime, timedelta
from typing import List, Optional

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user, restrict_superadmin
from modules.audit.service import log_audit_action
from .models import (
    EcritureCaisse,
    EcritureCaisseCreate,
    LibelleSuggestion,
)

router = APIRouter(
    tags=["Saisie Caisse"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("saisie_caisse"))],
)


# ─── Helpers: recalcul incrémental des soldes ───

def _is_position_before(a_date, a_id: int, b_date, b_id: int) -> bool:
    """Retourne True si (a_date, a_id) est avant (b_date, b_id) dans l'ordre chrono/id."""
    if a_date < b_date:
        return True
    if a_date > b_date:
        return False
    return a_id < b_id


def get_update_recalc_pivot(old_date, old_id: int, new_date, new_id: int):
    """Retourne le pivot minimal à recalculer lors d'un UPDATE.

    Si l'ancienne position est avant la nouvelle, on part de l'ancienne (zone déplacée + queue).
    Sinon, on part de la nouvelle.
    """
    if _is_position_before(old_date, old_id, new_date, new_id):
        return old_date, old_id
    return new_date, new_id


def recalculate_soldes_from(cursor, start_date, start_id: int):
    """Recalcule les soldes de manière incrémentale à partir d'un pivot (date, id).

    Couvre tous les scénarios :
    - insertion dans le passé (recalcul de la queue impactée)
    - modification de montant/date/libellé
    - suppression
    - déplacement d'une écriture (changement de date)
    """
    # Solde juste avant la zone à recalculer
    cursor.execute(
        """
        SELECT solde
        FROM ecritures_caisse
        WHERE date_ecriture < %s
           OR (date_ecriture = %s AND id < %s)
        ORDER BY date_ecriture DESC, id DESC
        LIMIT 1
        """,
        (start_date, start_date, start_id),
    )
    prev_row = cursor.fetchone()
    solde_cumul = float(prev_row["solde"]) if prev_row else 0.0

    # Recalcul uniquement de la partie impactée
    cursor.execute(
        """
        SELECT id, debit, credit
        FROM ecritures_caisse
        WHERE date_ecriture > %s
           OR (date_ecriture = %s AND id >= %s)
        ORDER BY date_ecriture ASC, id ASC
        """,
        (start_date, start_date, start_id),
    )
    impacted_rows = cursor.fetchall()

    for row in impacted_rows:
        solde_cumul += float(row["debit"]) - float(row["credit"])
        cursor.execute(
            "UPDATE ecritures_caisse SET solde = %s WHERE id = %s",
            (round(solde_cumul, 3), row["id"]),
        )


def update_libelle_frequent(libelle: str):
    """Mettre à jour le compteur d'utilisation d'un libellé"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO libelles_frequents (libelle, usage_count)
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE usage_count = usage_count + 1
        """, (libelle,))


# ═══════════════════════════════════════════════════════════
# 1. Routes CRUD – Écritures de caisse
# ═══════════════════════════════════════════════════════════

@router.post("/ecritures-caisse/", response_model=EcritureCaisse)
def create_ecriture_caisse(
    ecriture: EcritureCaisseCreate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ajouter une nouvelle écriture de caisse"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO ecritures_caisse 
            (date_ecriture, libelle_ecriture, debit, credit, solde)
            VALUES (%s, %s, %s, %s, 0)
        """, (ecriture.date_ecriture, ecriture.libelle_ecriture,
              ecriture.debit, ecriture.credit))

        ecriture_id = cursor.lastrowid

        recalculate_soldes_from(cursor, ecriture.date_ecriture, ecriture_id)

        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        update_libelle_frequent(ecriture.libelle_ecriture)

        ws_manager.broadcast("caisse", "create", {"id": ecriture_id})

        log_audit_action(
            user=user,
            action="create",
            module="saisie_caisse",
            entity_type="ecriture_caisse",
            entity_id=str(ecriture_id),
            detail={"date_ecriture": str(ecriture.date_ecriture), "libelle": ecriture.libelle_ecriture},
            request=request,
        )

        return result


@router.get("/ecritures-caisse/", response_model=List[EcritureCaisse])
def get_ecritures_caisse(
    skip: int = 0,
    limit: int = 100,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    migree: Optional[bool] = None,
):
    """Récupérer les écritures de caisse"""
    query = "SELECT * FROM ecritures_caisse WHERE 1=1"
    params = []

    if date_debut:
        query += " AND date_ecriture >= %s"
        params.append(date_debut)

    if date_fin:
        query += " AND date_ecriture <= %s"
        params.append(date_fin)

    if migree is not None:
        query += " AND est_migree = %s"
        params.append(migree)

    query += " ORDER BY date_ecriture DESC, id DESC LIMIT %s OFFSET %s"
    params.extend([limit, skip])

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


@router.get("/ecritures-caisse/{ecriture_id}", response_model=EcritureCaisse)
def get_ecriture_caisse(ecriture_id: int):
    """Récupérer une écriture de caisse par ID"""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Écriture non trouvée")

        return result


@router.put("/ecritures-caisse/{ecriture_id}")
def update_ecriture_caisse(
    ecriture_id: int,
    ecriture: EcritureCaisseCreate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Modifier une écriture de caisse"""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Écriture non trouvée")

        if existing['est_migree']:
            raise HTTPException(status_code=400, detail="Impossible de modifier une écriture migrée")

        old_date = existing['date_ecriture']
        old_id = int(existing['id'])

        cursor.execute("""
            UPDATE ecritures_caisse 
            SET date_ecriture = %s, libelle_ecriture = %s, debit = %s, credit = %s
            WHERE id = %s
        """, (ecriture.date_ecriture, ecriture.libelle_ecriture,
              ecriture.debit, ecriture.credit, ecriture_id))

        pivot_date, pivot_id = get_update_recalc_pivot(
            old_date,
            old_id,
            ecriture.date_ecriture,
            ecriture_id,
        )

        recalculate_soldes_from(cursor, pivot_date, pivot_id)

        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        ws_manager.broadcast("caisse", "update", {"id": ecriture_id})

        log_audit_action(
            user=user,
            action="update",
            module="saisie_caisse",
            entity_type="ecriture_caisse",
            entity_id=str(ecriture_id),
            detail={"date_ecriture": str(ecriture.date_ecriture), "libelle": ecriture.libelle_ecriture},
            request=request,
        )

        return result


@router.delete("/ecritures-caisse/{ecriture_id}")
def delete_ecriture_caisse(
    ecriture_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Supprimer une écriture de caisse"""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        ecriture = cursor.fetchone()

        if not ecriture:
            raise HTTPException(status_code=404, detail="Écriture non trouvée")

        if ecriture['est_migree']:
            raise HTTPException(status_code=400, detail="Impossible de supprimer une écriture migrée")

        deleted_date = ecriture['date_ecriture']
        deleted_id = int(ecriture['id'])

        cursor.execute("DELETE FROM ecritures_caisse WHERE id = %s", (ecriture_id,))

        recalculate_soldes_from(cursor, deleted_date, deleted_id)

        ws_manager.broadcast("caisse", "delete", {"id": ecriture_id})

        log_audit_action(
            user=user,
            action="delete",
            module="saisie_caisse",
            entity_type="ecriture_caisse",
            entity_id=str(ecriture_id),
            detail={"date_ecriture": str(deleted_date)},
            request=request,
        )

        return {"message": "Écriture supprimée avec succès"}


# ═══════════════════════════════════════════════════════════
# 2. Suggestions de libellés
# ═══════════════════════════════════════════════════════════

@router.get("/libelles-suggestions/", response_model=List[LibelleSuggestion])
def get_libelles_suggestions(search: str = ""):
    """Rechercher des libellés pour l'auto-complétion"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT libelle, compte_suggestion, tiers_suggestion, section_analytique_suggestion
            FROM libelles_frequents 
            WHERE libelle LIKE %s 
            ORDER BY usage_count DESC, libelle ASC 
            LIMIT 10
        """, (f"%{search}%",))
        return cursor.fetchall()


# ═══════════════════════════════════════════════════════════
# 3. Comptes
# ═══════════════════════════════════════════════════════════

@router.get("/comptes/")
def get_comptes(search: str = ""):
    """Récupérer la liste des comptes"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT code_compte, libelle_compte 
            FROM comptes 
            WHERE code_compte LIKE %s OR libelle_compte LIKE %s
            ORDER BY code_compte
            LIMIT 200
        """, (f"%{search}%", f"%{search}%"))
        return cursor.fetchall()


# ═══════════════════════════════════════════════════════════
# 4. Nettoyage historique migré
# ═══════════════════════════════════════════════════════════

@router.post("/nettoyer-historique-migre/")
def nettoyer_historique_migre(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Supprimer automatiquement les écritures migrées tout en conservant le solde.
    Crée une écriture de report à nouveau si nécessaire.
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT solde 
            FROM ecritures_caisse 
            ORDER BY date_ecriture DESC, id DESC 
            LIMIT 1
        """)
        dernier = cursor.fetchone()
        solde_actuel = float(dernier['solde']) if dernier else 0

        cursor.execute("SELECT COUNT(*) as count FROM ecritures_caisse WHERE est_migree = TRUE")
        count_result = cursor.fetchone()
        count_migrees = count_result['count']

        pivot_date = None
        pivot_id = None
        if count_migrees > 0:
            cursor.execute("""
                SELECT date_ecriture, MIN(id) AS min_id
                FROM ecritures_caisse
                WHERE est_migree = TRUE
                GROUP BY date_ecriture
                ORDER BY date_ecriture ASC
                LIMIT 1
            """)
            pivot = cursor.fetchone()
            if pivot:
                pivot_date = pivot['date_ecriture']
                pivot_id = int(pivot['min_id'])

        if count_migrees == 0:
            return {
                "message": "Aucune écriture migrée à nettoyer",
                "ecritures_supprimees": 0,
                "solde_reporte": solde_actuel,
            }

        cursor.execute("DELETE FROM ecritures_caisse WHERE est_migree = TRUE")

        cursor.execute("SELECT COUNT(*) as count FROM ecritures_caisse")
        remaining = cursor.fetchone()['count']

        if remaining == 0 and solde_actuel != 0:
            cursor.execute("""
                INSERT INTO ecritures_caisse 
                (date_ecriture, libelle_ecriture, debit, credit, solde, est_migree)
                VALUES (%s, %s, %s, %s, %s, FALSE)
            """, (
                date.today(),
                "📋 Report à nouveau",
                solde_actuel if solde_actuel > 0 else 0,
                abs(solde_actuel) if solde_actuel < 0 else 0,
                solde_actuel,
            ))
        elif remaining > 0:
            if pivot_date is not None and pivot_id is not None:
                recalculate_soldes_from(cursor, pivot_date, pivot_id)
            else:
                # Fallback de sécurité (cas inattendu)
                cursor.execute("""
                    SELECT date_ecriture, id
                    FROM ecritures_caisse
                    ORDER BY date_ecriture ASC, id ASC
                    LIMIT 1
                """)
                first_row = cursor.fetchone()
                if first_row:
                    recalculate_soldes_from(cursor, first_row['date_ecriture'], int(first_row['id']))

        ws_manager.broadcast("caisse", "cleanup", {"count": count_migrees})

        log_audit_action(
            user=user,
            action="cleanup",
            module="saisie_caisse",
            entity_type="ecritures_caisse",
            entity_id=None,
            detail={"ecritures_supprimees": count_migrees},
            request=request,
        )

        return {
            "message": f"Historique nettoyé: {count_migrees} écritures supprimées",
            "ecritures_supprimees": count_migrees,
            "solde_reporte": solde_actuel,
        }
