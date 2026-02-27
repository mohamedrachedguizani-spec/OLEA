# modules/saisie_caisse/router.py
from fastapi import APIRouter, HTTPException
from datetime import date, datetime, timedelta
from typing import List, Optional

from database import db
from ws_manager import manager as ws_manager
from .models import (
    EcritureCaisse,
    EcritureCaisseCreate,
    LibelleSuggestion,
)

router = APIRouter(
    tags=["Saisie Caisse"],
    responses={404: {"description": "Non trouvé"}},
)


# ─── Helper: recalculer TOUS les soldes de manière fiable ───

def recalculate_all_soldes(cursor):
    """Recalcule le solde cumulé de toutes les écritures dans l'ordre chronologique.
    C'est la seule méthode fiable car elle gère correctement :
    - Les insertions à des dates passées
    - Les modifications de date (changement de position)
    - Les suppressions
    """
    cursor.execute("""
        SELECT id, debit, credit 
        FROM ecritures_caisse 
        ORDER BY date_ecriture ASC, id ASC
    """)
    ecritures = cursor.fetchall()

    solde_cumul = 0
    for ec in ecritures:
        solde_cumul += float(ec['debit']) - float(ec['credit'])
        cursor.execute(
            "UPDATE ecritures_caisse SET solde = %s WHERE id = %s",
            (round(solde_cumul, 3), ec['id'])
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
def create_ecriture_caisse(ecriture: EcritureCaisseCreate):
    """Ajouter une nouvelle écriture de caisse"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO ecritures_caisse 
            (date_ecriture, libelle_ecriture, debit, credit, solde)
            VALUES (%s, %s, %s, %s, 0)
        """, (ecriture.date_ecriture, ecriture.libelle_ecriture,
              ecriture.debit, ecriture.credit))

        ecriture_id = cursor.lastrowid

        recalculate_all_soldes(cursor)

        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        update_libelle_frequent(ecriture.libelle_ecriture)

        ws_manager.broadcast("caisse", "create", {"id": ecriture_id})

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
def update_ecriture_caisse(ecriture_id: int, ecriture: EcritureCaisseCreate):
    """Modifier une écriture de caisse"""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Écriture non trouvée")

        if existing['est_migree']:
            raise HTTPException(status_code=400, detail="Impossible de modifier une écriture migrée")

        cursor.execute("""
            UPDATE ecritures_caisse 
            SET date_ecriture = %s, libelle_ecriture = %s, debit = %s, credit = %s
            WHERE id = %s
        """, (ecriture.date_ecriture, ecriture.libelle_ecriture,
              ecriture.debit, ecriture.credit, ecriture_id))

        recalculate_all_soldes(cursor)

        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        result = cursor.fetchone()

        ws_manager.broadcast("caisse", "update", {"id": ecriture_id})

        return result


@router.delete("/ecritures-caisse/{ecriture_id}")
def delete_ecriture_caisse(ecriture_id: int):
    """Supprimer une écriture de caisse"""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM ecritures_caisse WHERE id = %s", (ecriture_id,))
        ecriture = cursor.fetchone()

        if not ecriture:
            raise HTTPException(status_code=404, detail="Écriture non trouvée")

        if ecriture['est_migree']:
            raise HTTPException(status_code=400, detail="Impossible de supprimer une écriture migrée")

        cursor.execute("DELETE FROM ecritures_caisse WHERE id = %s", (ecriture_id,))

        recalculate_all_soldes(cursor)

        ws_manager.broadcast("caisse", "delete", {"id": ecriture_id})

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
def nettoyer_historique_migre():
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
            recalculate_all_soldes(cursor)

        ws_manager.broadcast("caisse", "cleanup", {"count": count_migrees})

        return {
            "message": f"Historique nettoyé: {count_migrees} écritures supprimées",
            "ecritures_supprimees": count_migrees,
            "solde_reporte": solde_actuel,
        }
