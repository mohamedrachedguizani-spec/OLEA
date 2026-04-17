# modules/migration_sage/router.py
from fastapi import APIRouter, HTTPException, Depends
from datetime import date
from typing import List, Optional

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user
from .models import (
    EcritureSage,
    EcritureSageCreate,
    MigrationRequest,
)

router = APIRouter(
    tags=["Migration Sage"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(get_current_user)],
)


# ═══════════════════════════════════════════════════════════
# 1. Écritures à migrer
# ═══════════════════════════════════════════════════════════

@router.get("/ecritures-a-migrer/", response_model=List[dict])
def get_ecritures_a_migrer():
    """Récupérer les écritures de caisse non migrées"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM ecritures_caisse 
            WHERE est_migree = FALSE 
            ORDER BY date_ecriture ASC, id ASC
        """)
        return cursor.fetchall()


# ═══════════════════════════════════════════════════════════
# 2. Migration d'une écriture
# ═══════════════════════════════════════════════════════════

@router.post("/migrer-ecriture/")
def migrer_ecriture(migration: MigrationRequest):
    """Migrer une écriture de caisse vers le format Sage (2 lignes)"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM ecritures_caisse 
            WHERE id = %s AND est_migree = FALSE
        """, (migration.ecriture_caisse_id,))
        ecriture_caisse = cursor.fetchone()

        if not ecriture_caisse:
            raise HTTPException(status_code=404, detail="Écriture non trouvée ou déjà migrée")

        numero_piece = f"MGCAI{ecriture_caisse['date_ecriture'].strftime('%m%Y')}"

        # Créer la première ligne (caisse)
        ligne1 = EcritureSageCreate(
            ecriture_caisse_id=ecriture_caisse['id'],
            date_compta=ecriture_caisse['date_ecriture'],
            compte=migration.ligne1.compte,
            tiers=migration.ligne1.tiers,
            montant_debit=ecriture_caisse['debit'],
            montant_credit=ecriture_caisse['credit'],
            section_analytique=migration.ligne1.section_analytique,
            numero_piece=numero_piece,
            libelle_ecriture=ecriture_caisse['libelle_ecriture'],
            societe="TN01",
            journal="CAI",
            devise="TND",
            type_piece="OD",
        )

        # Créer la deuxième ligne (compte correspondant — inversé)
        ligne2 = EcritureSageCreate(
            ecriture_caisse_id=ecriture_caisse['id'],
            date_compta=ecriture_caisse['date_ecriture'],
            compte=migration.ligne2.compte,
            tiers=migration.ligne2.tiers,
            montant_debit=ecriture_caisse['credit'],
            montant_credit=ecriture_caisse['debit'],
            section_analytique=migration.ligne2.section_analytique,
            numero_piece=numero_piece,
            libelle_ecriture=ecriture_caisse['libelle_ecriture'],
            societe="TN01",
            journal="CAI",
            devise="TND",
            type_piece="OD",
        )

        _insert_ecriture_sage(cursor, ligne1)
        _insert_ecriture_sage(cursor, ligne2)

        # Marquer comme migrée
        cursor.execute("""
            UPDATE ecritures_caisse 
            SET est_migree = TRUE 
            WHERE id = %s
        """, (ecriture_caisse['id'],))

        ws_manager.broadcast("migration", "migrate", {"id": ecriture_caisse['id']})
        # Notifier aussi la caisse (l'écriture est passée en migrée)
        ws_manager.broadcast("caisse", "update", {"id": ecriture_caisse['id']})

        return {
            "message": "Écriture migrée avec succès",
            "ecriture_caisse_id": ecriture_caisse['id'],
            "ligne1": ligne1,
            "ligne2": ligne2,
        }


@router.post("/migrer-tout/")
def migrer_tout(migrations: List[MigrationRequest]):
    """Migrer plusieurs écritures de caisse vers le format Sage"""
    resultats = []
    erreurs = []

    for migration in migrations:
        try:
            result = migrer_ecriture(migration)
            resultats.append(result)
        except Exception as e:
            erreurs.append({
                "ecriture_caisse_id": migration.ecriture_caisse_id,
                "erreur": str(e),
            })

    if resultats:
        ws_manager.broadcast("migration", "migrate_all", {"count": len(resultats)})
        ws_manager.broadcast("caisse", "update", {"bulk": True})

    return {
        "message": f"{len(resultats)} écritures migrées avec succès",
        "resultats": resultats,
        "erreurs": erreurs,
    }


# ═══════════════════════════════════════════════════════════
# 3. Écritures Sage (lecture)
# ═══════════════════════════════════════════════════════════

@router.get("/ecritures-sage/", response_model=List[EcritureSage])
def get_ecritures_sage(
    skip: int = 0,
    limit: int = 100,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
):
    """Récupérer les écritures au format Sage"""
    query = "SELECT * FROM ecritures_sage WHERE 1=1"
    params = []

    if date_debut:
        query += " AND date_compta >= %s"
        params.append(date_debut)

    if date_fin:
        query += " AND date_compta <= %s"
        params.append(date_fin)

    query += " ORDER BY date_compta DESC, id DESC LIMIT %s OFFSET %s"
    params.extend([limit, skip])

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


# ═══════════════════════════════════════════════════════════
# 4. Vérification de la balance
# ═══════════════════════════════════════════════════════════

@router.get("/verifier-balance/")
def verifier_balance():
    """Vérifier que toutes les écritures sont équilibrées"""
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT 
                numero_piece,
                SUM(montant_debit) as total_debit,
                SUM(montant_credit) as total_credit,
                SUM(montant_debit) - SUM(montant_credit) as difference
            FROM ecritures_sage
            GROUP BY numero_piece
            HAVING ABS(SUM(montant_debit) - SUM(montant_credit)) > 0.001
        """)
        desequilibres = cursor.fetchall()

        cursor.execute("""
            SELECT 
                COUNT(*) as total_ecritures,
                SUM(montant_debit) as total_debit,
                SUM(montant_credit) as total_credit,
                SUM(montant_debit) - SUM(montant_credit) as difference
            FROM ecritures_sage
        """)
        total = cursor.fetchone()

        return {
            "total_ecritures": total['total_ecritures'],
            "total_debit": total['total_debit'],
            "total_credit": total['total_credit'],
            "difference": total['difference'],
            "desequilibres": desequilibres,
        }


# ─── Helper privé ───

def _insert_ecriture_sage(cursor, ligne: EcritureSageCreate):
    """Insère une ligne d'écriture Sage en BDD"""
    cursor.execute("""
        INSERT INTO ecritures_sage 
        (ecriture_caisse_id, societe, journal, date_compta, compte, tiers, 
         montant_debit, montant_credit, section_analytique, numero_piece, 
         libelle_ecriture, devise, type_piece)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        ligne.ecriture_caisse_id, ligne.societe, ligne.journal, ligne.date_compta,
        ligne.compte, ligne.tiers, ligne.montant_debit, ligne.montant_credit,
        ligne.section_analytique, ligne.numero_piece, ligne.libelle_ecriture,
        ligne.devise, ligne.type_piece,
    ))
