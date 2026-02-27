# modules/dashboard/router.py
"""
Module dédié au tableau de bord global.
Agrège les données de tous les modules : Caisse, Migration Sage, BFC.
"""
import json
from fastapi import APIRouter, HTTPException
from datetime import date, datetime, timedelta
from typing import Optional

from database import db

router = APIRouter(
    tags=["Dashboard Global"],
    responses={404: {"description": "Non trouvé"}},
)


@router.get("/global-dashboard/")
def get_global_dashboard(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
):
    """
    Endpoint principal du tableau de bord global.
    Agrège les statistiques de tous les modules :
      - Trésorerie (caisse)
      - Migration Sage
      - Analyse financière (BFC)
    """
    with db.get_cursor() as cursor:
        caisse = _get_caisse_stats(cursor, date_debut, date_fin)
        migration = _get_migration_stats(cursor)
        bfc = _get_bfc_stats(cursor)

    return {
        "caisse": caisse,
        "migration": migration,
        "bfc": bfc,
    }


# ═══════════════════════════════════════════════════════════
# SECTION 1 — Statistiques Caisse (Trésorerie)
# ═══════════════════════════════════════════════════════════

def _get_caisse_stats(cursor, date_debut, date_fin):
    where_clause = "WHERE 1=1"
    params = []

    if date_debut:
        where_clause += " AND date_ecriture >= %s"
        params.append(date_debut)
    if date_fin:
        where_clause += " AND date_ecriture <= %s"
        params.append(date_fin)

    # ── KPIs principaux ──
    cursor.execute(f"""
        SELECT 
            COALESCE(SUM(debit), 0)  AS total_debit,
            COALESCE(SUM(credit), 0) AS total_credit,
            COUNT(*)                 AS nombre_ecritures,
            COUNT(CASE WHEN est_migree = TRUE  THEN 1 END) AS ecritures_migrees,
            COUNT(CASE WHEN est_migree = FALSE THEN 1 END) AS ecritures_en_attente
        FROM ecritures_caisse
        {where_clause}
    """, params)
    stats = cursor.fetchone()

    # ── Solde actuel (global, sans filtre de dates) ──
    cursor.execute("""
        SELECT solde 
        FROM ecritures_caisse 
        ORDER BY date_ecriture DESC, id DESC 
        LIMIT 1
    """)
    dernier_solde = cursor.fetchone()
    solde_actuel = float(dernier_solde['solde']) if dernier_solde else 0

    # ── Évolution journalière (flux de trésorerie) ──
    cursor.execute(f"""
        SELECT 
            DATE(date_ecriture) AS jour,
            COALESCE(SUM(debit), 0) AS debit,
            COALESCE(SUM(credit), 0) AS credit
        FROM ecritures_caisse
        {where_clause}
        GROUP BY DATE(date_ecriture)
        ORDER BY jour ASC
        LIMIT 60
    """, params)
    evolution_rows = cursor.fetchall()

    # ── Solde cumulé par jour (pour le graphe Area) ──
    solde_cumul = 0
    evolution = []
    for e in evolution_rows:
        d = float(e['debit'])
        c = float(e['credit'])
        solde_cumul += d - c
        evolution.append({
            "jour": str(e['jour']),
            "debit": d,
            "credit": c,
            "solde_cumul": round(solde_cumul, 3),
        })

    # ── Top 7 libellés (plus exploitable qu'un top 5) ──
    cursor.execute(f"""
        SELECT 
            libelle_ecriture AS libelle,
            COUNT(*)                 AS occurrences,
            COALESCE(SUM(debit), 0)  AS total_debit,
            COALESCE(SUM(credit), 0) AS total_credit
        FROM ecritures_caisse
        {where_clause}
        GROUP BY libelle_ecriture
        ORDER BY occurrences DESC
        LIMIT 7
    """, params)
    top_libelles = [
        {
            "libelle": t['libelle'],
            "occurrences": t['occurrences'],
            "total_debit": float(t['total_debit']),
            "total_credit": float(t['total_credit']),
            "net": round(float(t['total_debit']) - float(t['total_credit']), 3),
        }
        for t in cursor.fetchall()
    ]

    # ── Répartition débit/crédit par semaine (tendance) ──
    cursor.execute(f"""
        SELECT 
            YEARWEEK(date_ecriture, 1) AS semaine,
            MIN(DATE(date_ecriture))   AS debut_semaine,
            COALESCE(SUM(debit), 0)    AS debit,
            COALESCE(SUM(credit), 0)   AS credit,
            COUNT(*)                   AS nb_ecritures
        FROM ecritures_caisse
        {where_clause}
        GROUP BY YEARWEEK(date_ecriture, 1)
        ORDER BY semaine ASC
        LIMIT 26
    """, params)
    tendance_hebdo = [
        {
            "semaine": str(r['debut_semaine']),
            "debit": float(r['debit']),
            "credit": float(r['credit']),
            "nb_ecritures": r['nb_ecritures'],
        }
        for r in cursor.fetchall()
    ]

    return {
        "solde_actuel": solde_actuel,
        "total_debit": float(stats['total_debit']),
        "total_credit": float(stats['total_credit']),
        "nombre_ecritures": stats['nombre_ecritures'],
        "ecritures_migrees": stats['ecritures_migrees'],
        "ecritures_en_attente": stats['ecritures_en_attente'],
        "evolution": evolution,
        "top_libelles": top_libelles,
        "tendance_hebdo": tendance_hebdo,
    }


# ═══════════════════════════════════════════════════════════
# SECTION 2 — Statistiques Migration Sage
# ═══════════════════════════════════════════════════════════

def _get_migration_stats(cursor):
    # ── Volume migré ──
    cursor.execute("""
        SELECT 
            COUNT(*)                        AS total_ecritures,
            COALESCE(SUM(montant_debit), 0) AS total_debit,
            COALESCE(SUM(montant_credit), 0) AS total_credit,
            COUNT(DISTINCT numero_piece)     AS nb_pieces,
            COUNT(DISTINCT compte)           AS nb_comptes
        FROM ecritures_sage
    """)
    vol = cursor.fetchone()

    # ── Balance ──
    total_debit = float(vol['total_debit']) if vol['total_debit'] else 0
    total_credit = float(vol['total_credit']) if vol['total_credit'] else 0
    difference = round(total_debit - total_credit, 3)

    # ── Pièces en déséquilibre ──
    cursor.execute("""
        SELECT COUNT(*) AS nb
        FROM (
            SELECT numero_piece
            FROM ecritures_sage
            GROUP BY numero_piece
            HAVING ABS(SUM(montant_debit) - SUM(montant_credit)) > 0.001
        ) sub
    """)
    nb_deseq = cursor.fetchone()['nb']

    # ── Évolution mensuelle des migrations ──
    cursor.execute("""
        SELECT 
            DATE_FORMAT(date_compta, '%%Y-%%m') AS mois,
            COUNT(*)                             AS nb_ecritures,
            COALESCE(SUM(montant_debit), 0)      AS debit,
            COALESCE(SUM(montant_credit), 0)     AS credit
        FROM ecritures_sage
        GROUP BY DATE_FORMAT(date_compta, '%%Y-%%m')
        ORDER BY mois ASC
        LIMIT 12
    """)
    evolution_mensuelle = [
        {
            "mois": r['mois'],
            "nb_ecritures": r['nb_ecritures'],
            "debit": float(r['debit']),
            "credit": float(r['credit']),
        }
        for r in cursor.fetchall()
    ]

    # ── Top comptes utilisés ──
    cursor.execute("""
        SELECT 
            compte,
            COUNT(*) AS occurrences,
            COALESCE(SUM(montant_debit), 0) AS total_debit,
            COALESCE(SUM(montant_credit), 0) AS total_credit
        FROM ecritures_sage
        GROUP BY compte
        ORDER BY occurrences DESC
        LIMIT 5
    """)
    top_comptes = [
        {
            "compte": r['compte'],
            "occurrences": r['occurrences'],
            "total_debit": float(r['total_debit']),
            "total_credit": float(r['total_credit']),
        }
        for r in cursor.fetchall()
    ]

    return {
        "total_ecritures": vol['total_ecritures'],
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": difference,
        "equilibre": abs(difference) < 0.01,
        "nb_pieces": vol['nb_pieces'],
        "nb_comptes": vol['nb_comptes'],
        "nb_desequilibres": nb_deseq,
        "evolution_mensuelle": evolution_mensuelle,
        "top_comptes": top_comptes,
    }


# ═══════════════════════════════════════════════════════════
# SECTION 3 — Statistiques BFC (Analyse Financière)
# ═══════════════════════════════════════════════════════════

def _get_bfc_stats(cursor):
    # ── Nombre de périodes ──
    cursor.execute("SELECT COUNT(*) AS nb FROM sage_bfc_monthly")
    nb_periodes = cursor.fetchone()['nb']

    if nb_periodes == 0:
        return {
            "nb_periodes": 0,
            "tendance": [],
            "derniere_periode": None,
            "pnl_detail": None,
        }

    # ── Tendance mensuelle : CA Net, EBITDA, Résultat Net ──
    cursor.execute("""
        SELECT periode, resume
        FROM sage_bfc_monthly
        ORDER BY periode ASC
    """)
    rows = cursor.fetchall()

    tendance = []
    derniere_periode = None
    dernier_resume = None

    for row in rows:
        resume = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
        periode_str = str(row['periode'])[:7]  # YYYY-MM

        tendance.append({
            "periode": periode_str,
            "ca_net": float(resume.get('ca_net', 0)),
            "ebitda": float(resume.get('ebitda', 0)),
            "ebitda_pct": float(resume.get('ebitda_pct', 0)),
            "resultat_net": float(resume.get('resultat_net', 0)),
            "resultat_net_pct": float(resume.get('resultat_net_pct', 0)),
            "total_produits": float(resume.get('total_produits', 0)),
            "total_charges": float(resume.get('total_charges', 0)),
        })

        derniere_periode = periode_str
        dernier_resume = resume

    # ── P&L détaillé du dernier mois ──
    pnl_detail = None
    if dernier_resume:
        pnl_detail = {
            "ca_brut": float(dernier_resume.get('ca_brut', 0)),
            "retrocessions": float(dernier_resume.get('retrocessions', 0)),
            "ca_net": float(dernier_resume.get('ca_net', 0)),
            "autres_produits": float(dernier_resume.get('autres_produits', 0)),
            "total_produits": float(dernier_resume.get('total_produits', 0)),
            "frais_personnel": float(dernier_resume.get('frais_personnel', 0)),
            "honoraires": float(dernier_resume.get('honoraires', 0)),
            "frais_commerciaux": float(dernier_resume.get('frais_commerciaux', 0)),
            "impots_taxes": float(dernier_resume.get('impots_taxes', 0)),
            "fonctionnement": float(dernier_resume.get('fonctionnement', 0)),
            "autres_charges": float(dernier_resume.get('autres_charges', 0)),
            "total_charges": float(dernier_resume.get('total_charges', 0)),
            "ebitda": float(dernier_resume.get('ebitda', 0)),
            "ebitda_pct": float(dernier_resume.get('ebitda_pct', 0)),
            "produits_financiers": float(dernier_resume.get('produits_financiers', 0)),
            "charges_financieres": float(dernier_resume.get('charges_financieres', 0)),
            "resultat_financier": float(dernier_resume.get('resultat_financier', 0)),
            "dotations": float(dernier_resume.get('dotations', 0)),
            "resultat_avant_impot": float(dernier_resume.get('resultat_avant_impot', 0)),
            "impot_societes": float(dernier_resume.get('impot_societes', 0)),
            "resultat_net": float(dernier_resume.get('resultat_net', 0)),
            "resultat_net_pct": float(dernier_resume.get('resultat_net_pct', 0)),
        }

    return {
        "nb_periodes": nb_periodes,
        "tendance": tendance,
        "derniere_periode": derniere_periode,
        "pnl_detail": pnl_detail,
    }
