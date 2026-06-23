# modules/saisie_caisse/router.py
from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import date, datetime, timedelta
from typing import List, Optional
import math

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user, restrict_superadmin
from modules.audit.service import log_audit_action
from .models import (
    EcritureCaisse,
    EcritureCaisseCreate,
    EcritureCaissePage,
    LibelleSuggestion,
)

SELECT_FIELDS_WITH_ADJUSTED_SOLDE = """
    id, date_ecriture, libelle_ecriture, debit, credit, est_migree, created_at, compte_contrepartie, tiers, section_analytique,
    (solde + COALESCE((
        SELECT SUM(sub.debit - sub.credit) 
        FROM ecritures_caisse AS sub 
        WHERE sub.est_migree = TRUE 
          AND (sub.date_ecriture > ecritures_caisse.date_ecriture 
               OR (sub.date_ecriture = ecritures_caisse.date_ecriture AND sub.id > ecritures_caisse.id))
    ), 0)) AS solde
"""


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


def update_libelle_frequent(
    libelle: str,
    compte: Optional[str] = None,
    tiers: Optional[str] = None,
    section: Optional[str] = None,
):
    """Mettre à jour le compteur d'utilisation d'un libellé et enregistrer les suggestions"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO libelles_frequents (libelle, compte_suggestion, tiers_suggestion, section_analytique_suggestion, usage_count)
            VALUES (%s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE 
                usage_count = usage_count + 1,
                compte_suggestion = COALESCE(%s, compte_suggestion),
                tiers_suggestion = COALESCE(%s, tiers_suggestion),
                section_analytique_suggestion = COALESCE(%s, section_analytique_suggestion)
        """, (libelle, compte, tiers, section, compte, tiers, section))


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
            (date_ecriture, libelle_ecriture, debit, credit, solde, compte_contrepartie, tiers, section_analytique)
            VALUES (%s, %s, %s, %s, 0, %s, %s, %s)
        """, (ecriture.date_ecriture, ecriture.libelle_ecriture,
              ecriture.debit, ecriture.credit, ecriture.compte_contrepartie,
              ecriture.tiers, ecriture.section_analytique))

        ecriture_id = cursor.lastrowid

        recalculate_soldes_from(cursor, ecriture.date_ecriture, ecriture_id)

        cursor.execute(f"SELECT {SELECT_FIELDS_WITH_ADJUSTED_SOLDE} FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        update_libelle_frequent(
            ecriture.libelle_ecriture,
            ecriture.compte_contrepartie,
            ecriture.tiers,
            ecriture.section_analytique
        )

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


@router.get("/ecritures-caisse/", response_model=EcritureCaissePage)
def get_ecritures_caisse(
    page: int = 1,
    page_size: int = 20,
    order: str = "desc",
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    migree: Optional[bool] = None,
):
    """Récupérer les écritures de caisse (paginé)"""
    safe_page = max(1, page)
    safe_page_size = max(1, page_size)
    offset = (safe_page - 1) * safe_page_size
    safe_order = "DESC" if order.lower() == "desc" else "ASC"

    base_query = "FROM ecritures_caisse WHERE 1=1"
    params = []

    if date_debut:
        base_query += " AND date_ecriture >= %s"
        params.append(date_debut)

    if date_fin:
        base_query += " AND date_ecriture <= %s"
        params.append(date_fin)

    if migree is not None:
        base_query += " AND est_migree = %s"
        params.append(migree)

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) as cnt {base_query}", params)
        row = cursor.fetchone()
        total = int(row["cnt"] if row else 0)

        cursor.execute(
            f"SELECT {SELECT_FIELDS_WITH_ADJUSTED_SOLDE} {base_query} ORDER BY date_ecriture {safe_order}, id {safe_order} LIMIT %s OFFSET %s",
            params + [safe_page_size, offset],
        )
        items = cursor.fetchall()

    pages = max(1, math.ceil(total / safe_page_size))
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "pages": pages,
    }


@router.get("/ecritures-caisse/{ecriture_id}", response_model=EcritureCaisse)
def get_ecriture_caisse(ecriture_id: int):
    """Récupérer une écriture de caisse par ID"""
    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT {SELECT_FIELDS_WITH_ADJUSTED_SOLDE} FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
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
            SET date_ecriture = %s, libelle_ecriture = %s, debit = %s, credit = %s,
                compte_contrepartie = %s, tiers = %s, section_analytique = %s
            WHERE id = %s
        """, (ecriture.date_ecriture, ecriture.libelle_ecriture,
              ecriture.debit, ecriture.credit, ecriture.compte_contrepartie,
              ecriture.tiers, ecriture.section_analytique, ecriture_id))

        pivot_date, pivot_id = get_update_recalc_pivot(
            old_date,
            old_id,
            ecriture.date_ecriture,
            ecriture_id,
        )

        recalculate_soldes_from(cursor, pivot_date, pivot_id)

        cursor.execute(f"SELECT {SELECT_FIELDS_WITH_ADJUSTED_SOLDE} FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        ws_manager.broadcast("caisse", "update", {"id": ecriture_id})

        log_audit_action(
            user=user,
            action="update",
            module="saisie_caisse",
            entity_type="ecriture_caisse",
            entity_id=str(ecriture_id),
            detail={
                "before": {
                    "date_ecriture": str(existing.get("date_ecriture")) if existing else None,
                    "libelle_ecriture": existing.get("libelle_ecriture") if existing else None,
                    "debit": float(existing.get("debit")) if existing else None,
                    "credit": float(existing.get("credit")) if existing else None,
                    "compte_contrepartie": existing.get("compte_contrepartie") if existing else None,
                    "tiers": existing.get("tiers") if existing else None,
                    "section_analytique": existing.get("section_analytique") if existing else None,
                },
                "after": {
                    "date_ecriture": str(ecriture.date_ecriture),
                    "libelle_ecriture": ecriture.libelle_ecriture,
                    "debit": float(ecriture.debit),
                    "credit": float(ecriture.credit),
                    "compte_contrepartie": ecriture.compte_contrepartie,
                    "tiers": ecriture.tiers,
                    "section_analytique": ecriture.section_analytique,
                },
            },
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
# 3.5 Tiers
# ═══════════════════════════════════════════════════════════

@router.get("/tiers/")
def get_tiers(search: str = ""):
    """Récupérer la liste des tiers"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT code, libelle 
            FROM plan_tiers 
            WHERE code LIKE %s OR libelle LIKE %s
            ORDER BY code
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
    Supprimer automatiquement les écritures migrées situées avant la plus ancienne écriture non migrée
    tout en conservant le solde cumulé exact à l'aide d'un Report à nouveau historique.
    """
    from datetime import timedelta
    with db.get_cursor() as cursor:
        # Trouver la plus ancienne écriture non migrée
        cursor.execute("""
            SELECT date_ecriture, id 
            FROM ecritures_caisse 
            WHERE est_migree = FALSE 
            ORDER BY date_ecriture ASC, id ASC 
            LIMIT 1
        """)
        oldest_active = cursor.fetchone()

        # Si toutes les écritures sont migrées
        if not oldest_active:
            cursor.execute("""
                SELECT solde 
                FROM ecritures_caisse 
                ORDER BY date_ecriture DESC, id DESC 
                LIMIT 1
            """)
            dernier = cursor.fetchone()
            solde_actuel = float(dernier['solde']) if dernier else 0.0

            cursor.execute("SELECT COUNT(*) as count FROM ecritures_caisse")
            total_count = cursor.fetchone()['count']

            if total_count > 0:
                cursor.execute("DELETE FROM ecritures_caisse")
                if solde_actuel != 0:
                    cursor.execute("""
                        INSERT INTO ecritures_caisse 
                        (date_ecriture, libelle_ecriture, debit, credit, solde, est_migree)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                    """, (
                        date.today(),
                        "📋 Report à nouveau",
                        solde_actuel if solde_actuel > 0 else 0,
                        abs(solde_actuel) if solde_actuel < 0 else 0,
                        solde_actuel,
                    ))
                ws_manager.broadcast("caisse", "cleanup", {"count": total_count})
                
                log_audit_action(
                    user=user,
                    action="cleanup",
                    module="saisie_caisse",
                    entity_type="ecritures_caisse",
                    entity_id=None,
                    detail={"ecritures_supprimees": total_count},
                    request=request,
                )
                return {
                    "message": f"Historique nettoyé: {total_count} écritures supprimées",
                    "ecritures_supprimees": total_count,
                    "solde_reporte": solde_actuel,
                }
            else:
                return {
                    "message": "Aucune écriture migrée à nettoyer",
                    "ecritures_supprimees": 0,
                    "solde_reporte": 0,
                }

        # S'il y a des écritures actives
        # 1. Calculer le solde cumulé immédiatement avant la plus ancienne active
        cursor.execute("""
            SELECT solde 
            FROM ecritures_caisse 
            WHERE date_ecriture < %s OR (date_ecriture = %s AND id < %s)
            ORDER BY date_ecriture DESC, id DESC 
            LIMIT 1
        """, (oldest_active['date_ecriture'], oldest_active['date_ecriture'], oldest_active['id']))
        dernier_migre = cursor.fetchone()
        solde_before = float(dernier_migre['solde']) if dernier_migre else 0.0

        # 2. Compter les écritures migrées à supprimer (celles situées avant oldest_active)
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM ecritures_caisse 
            WHERE est_migree = TRUE 
              AND (date_ecriture < %s OR (date_ecriture = %s AND id < %s))
        """, (oldest_active['date_ecriture'], oldest_active['date_ecriture'], oldest_active['id']))
        count_migrees = cursor.fetchone()['count']

        if count_migrees == 0:
            return {
                "message": "Aucune écriture migrée ancienne à nettoyer",
                "ecritures_supprimees": 0,
                "solde_reporte": solde_before,
            }

        # 3. Supprimer les écritures migrées anciennes
        cursor.execute("""
            DELETE FROM ecritures_caisse 
            WHERE est_migree = TRUE 
              AND (date_ecriture < %s OR (date_ecriture = %s AND id < %s))
        """, (oldest_active['date_ecriture'], oldest_active['date_ecriture'], oldest_active['id']))

        # 4. Créer un Report à nouveau si solde_before != 0
        date_report = oldest_active['date_ecriture'] - timedelta(days=1)
        if solde_before != 0:
            cursor.execute("""
                INSERT INTO ecritures_caisse 
                (date_ecriture, libelle_ecriture, debit, credit, solde, est_migree)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (
                date_report,
                "📋 Report à nouveau (Historique migré)",
                solde_before if solde_before > 0 else 0,
                abs(solde_before) if solde_before < 0 else 0,
                solde_before,
            ))
            report_id = cursor.lastrowid
            recalculate_soldes_from(cursor, date_report, report_id)
        else:
            recalculate_soldes_from(cursor, oldest_active['date_ecriture'], oldest_active['id'])

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
            "solde_reporte": solde_before,
        }
