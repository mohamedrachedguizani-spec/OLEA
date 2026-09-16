# modules/dashboard/router.py
"""
Module dédié au tableau de bord global.
Agrège les données de tous les modules : Caisse, Migration Sage, BFC.
"""
import json
from fastapi import APIRouter, HTTPException, Depends
from datetime import date, datetime, timedelta
from typing import Optional

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import require_permission_code

router = APIRouter(
    tags=["Dashboard Global"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[],
)


def _get_users_stats(cursor):
    cursor.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(is_active = TRUE) AS active, "
        "SUM(is_active = FALSE) AS inactive "
        "FROM users"
    )
    totals = cursor.fetchone() or {"total": 0, "active": 0, "inactive": 0}

    cursor.execute("SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
    roles_rows = cursor.fetchall()
    roles = {row["role"]: row["cnt"] for row in roles_rows}

    cursor.execute(
        "SELECT id, username, email, role, is_active, created_at "
        "FROM users ORDER BY created_at DESC LIMIT 5"
    )
    recent_users = cursor.fetchall()

    return {
        "total": int(totals.get("total") or 0),
        "active": int(totals.get("active") or 0),
        "inactive": int(totals.get("inactive") or 0),
        "roles": roles,
        "recent_users": recent_users,
    }


def _get_sessions_stats(cursor):
    cursor.execute(
        "SELECT COUNT(*) AS total_sessions, COUNT(DISTINCT us.user_id) AS active_users "
        "FROM user_sessions us "
        "JOIN users u ON u.id = us.user_id "
        "WHERE us.token_version = u.token_version "
        "AND us.last_seen_at > NOW() - INTERVAL 45 SECOND"
    )
    row = cursor.fetchone() or {"total_sessions": 0, "active_users": 0}
    return {
        "total_sessions": int(row.get("total_sessions") or 0),
        "active_users": int(row.get("active_users") or 0),
    }


def _build_audit_date_filter(date_debut: Optional[date], date_fin: Optional[date]):
    where_clause = "WHERE 1=1"
    params: list = []

    if date_debut:
        start_dt = datetime.combine(date_debut, datetime.min.time())
        where_clause += " AND created_at >= %s"
        params.append(start_dt)

    if date_fin:
        end_dt = datetime.combine(date_fin + timedelta(days=1), datetime.min.time())
        where_clause += " AND created_at < %s"
        params.append(end_dt)

    return where_clause, params


def _get_audit_stats(cursor, date_debut: Optional[date], date_fin: Optional[date]):
    where_clause, params = _build_audit_date_filter(date_debut, date_fin)

    cursor.execute(
        f"SELECT COUNT(*) AS total_24h FROM audit_logs {where_clause} "
        "AND created_at > NOW() - INTERVAL 1 DAY",
        params,
    )
    total_24h = int((cursor.fetchone() or {}).get("total_24h") or 0)

    cursor.execute(
        f"SELECT COUNT(*) AS total_7d FROM audit_logs {where_clause} "
        "AND created_at > NOW() - INTERVAL 7 DAY",
        params,
    )
    total_7d = int((cursor.fetchone() or {}).get("total_7d") or 0)

    cursor.execute(
        f"SELECT module, COUNT(*) AS cnt FROM audit_logs {where_clause} "
        "AND created_at > NOW() - INTERVAL 7 DAY "
        "GROUP BY module ORDER BY cnt DESC",
        params,
    )
    by_module = cursor.fetchall()

    cursor.execute(
        f"SELECT DATE(created_at) AS day, COUNT(*) AS cnt FROM audit_logs {where_clause} "
        "AND created_at > NOW() - INTERVAL 14 DAY "
        "GROUP BY DATE(created_at) ORDER BY day ASC",
        params,
    )
    timeline = cursor.fetchall()

    cursor.execute(
        f"SELECT username, action, module, ip_address, created_at "
        f"FROM audit_logs {where_clause} "
        "ORDER BY created_at DESC LIMIT 10",
        params,
    )
    recent = cursor.fetchall()

    return {
        "total_24h": total_24h,
        "total_7d": total_7d,
        "by_module": by_module,
        "timeline": timeline,
        "recent": recent,
    }


@router.get("/global-dashboard/")
def get_global_dashboard(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    _user: dict = Depends(require_permission_code("dashboard.read")),
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
        migration = _get_migration_stats(cursor, date_debut, date_fin)
        bfc = _get_bfc_stats(cursor, date_debut, date_fin)
        latest_bfc = _get_latest_bfc_year_kpis(cursor)
        overview = _get_overview_stats(cursor, caisse, migration, bfc, latest_bfc, date_debut, date_fin)

    return {
        "caisse": caisse,
        "migration": migration,
        "bfc": bfc,
        "overview": overview,
    }


@router.get("/admin-dashboard/")
def get_admin_dashboard(
    _admin: dict = Depends(require_permission_code("admin.dashboard.read")),
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
):
    """
    Tableau de bord dédié au superadmin.
    Fournit des KPI utilisateurs, sessions et audit.
    """
    with db.get_cursor() as cursor:
        users = _get_users_stats(cursor)
        sessions = _get_sessions_stats(cursor)
        audit = _get_audit_stats(cursor, date_debut, date_fin)

    return {
        "users": users,
        "sessions": sessions,
        "audit": audit,
        "realtime": {"ws_clients": ws_manager.active_count},
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

def _get_migration_stats(cursor, date_debut=None, date_fin=None):
    where_clause = "WHERE 1=1"
    params = []
    if date_debut:
        where_clause += " AND date_compta >= %s"
        params.append(date_debut)
    if date_fin:
        where_clause += " AND date_compta <= %s"
        params.append(date_fin)

    # ── Volume migré ──
    cursor.execute(f"""
        SELECT 
            COUNT(*)                        AS total_ecritures,
            COALESCE(SUM(montant_debit), 0) AS total_debit,
            COALESCE(SUM(montant_credit), 0) AS total_credit,
            COUNT(DISTINCT numero_piece)     AS nb_pieces,
            COUNT(DISTINCT compte)           AS nb_comptes
        FROM ecritures_sage
        {where_clause}
    """, params)
    vol = cursor.fetchone()

    # ── Balance ──
    total_debit = float(vol['total_debit']) if vol['total_debit'] else 0
    total_credit = float(vol['total_credit']) if vol['total_credit'] else 0
    difference = round(total_debit - total_credit, 3)

    # ── Pièces en déséquilibre ──
    cursor.execute(f"""
        SELECT COUNT(*) AS nb
        FROM (
            SELECT numero_piece
            FROM ecritures_sage
            {where_clause}
            GROUP BY numero_piece
            HAVING ABS(SUM(montant_debit) - SUM(montant_credit)) > 0.001
        ) sub
    """, params)
    nb_deseq = cursor.fetchone()['nb']

    # ── Évolution mensuelle des migrations ──
    cursor.execute(f"""
        SELECT 
            DATE_FORMAT(date_compta, '%%Y-%%m') AS mois,
            COUNT(*)                             AS nb_ecritures,
            COALESCE(SUM(montant_debit), 0)      AS debit,
            COALESCE(SUM(montant_credit), 0)     AS credit
        FROM ecritures_sage
        {where_clause}
        GROUP BY DATE_FORMAT(date_compta, '%%Y-%%m')
        ORDER BY mois ASC
        LIMIT 12
    """, params)
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
    cursor.execute(f"""
        SELECT 
            compte,
            COUNT(*) AS occurrences,
            COALESCE(SUM(montant_debit), 0) AS total_debit,
            COALESCE(SUM(montant_credit), 0) AS total_credit
        FROM ecritures_sage
        {where_clause}
        GROUP BY compte
        ORDER BY occurrences DESC
        LIMIT 5
    """, params)
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

BFC_CUMUL_KEYS = (
    "ca_brut", "retrocessions", "ca_net", "autres_produits", "total_produits",
    "frais_personnel", "honoraires", "frais_commerciaux", "impots_taxes",
    "fonctionnement", "autres_charges", "total_charges", "ebitda",
    "produits_financiers", "charges_financieres", "resultat_financier",
    "resultat_exceptionnel", "dotations", "resultat_avant_impot",
    "impot_societes", "resultat_net",
)


def _month_start(value: Optional[date]):
    return date(value.year, value.month, 1) if value else None


def _previous_year(value: Optional[date]):
    if not value:
        return None
    try:
        return value.replace(year=value.year - 1)
    except ValueError:  # 29 février
        return value.replace(year=value.year - 1, day=28)


def _bfc_where(date_debut: Optional[date], date_fin: Optional[date]):
    clauses = []
    params = []
    if date_debut:
        clauses.append("periode >= %s")
        params.append(_month_start(date_debut))
    if date_fin:
        clauses.append("periode <= %s")
        params.append(_month_start(date_fin))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _decode_resume(raw_resume):
    return raw_resume if isinstance(raw_resume, dict) else json.loads(raw_resume)


def _aggregate_bfc(rows):
    totals = {key: 0.0 for key in BFC_CUMUL_KEYS}
    for row in rows:
        resume = _decode_resume(row["resume"])
        for key in BFC_CUMUL_KEYS:
            totals[key] += float(resume.get(key, 0) or 0)
    totals["ebitda_pct"] = (totals["ebitda"] / totals["ca_net"] * 100) if totals["ca_net"] else 0.0
    totals["resultat_net_pct"] = (totals["resultat_net"] / totals["ca_net"] * 100) if totals["ca_net"] else 0.0
    return totals


def _build_bfc_decision_data(current, previous, has_previous):
    charge_labels = (
        ("Personnel", "frais_personnel"),
        ("Honoraires", "honoraires"),
        ("Commercial", "frais_commerciaux"),
        ("Impôts & taxes", "impots_taxes"),
        ("Fonctionnement", "fonctionnement"),
        ("Autres charges", "autres_charges"),
    )
    charge_structure = [
        {"name": label, "value": abs(current[key])}
        for label, key in charge_labels
        if abs(current[key]) > 0
    ]

    comparison = []
    for label, key in (
        ("CA Net", "ca_net"),
        ("EBITDA", "ebitda"),
        ("Résultat financier", "resultat_financier"),
        ("Résultat net", "resultat_net"),
    ):
        prior_value = previous[key] if has_previous else 0.0
        evolution = ((current[key] - prior_value) / abs(prior_value) * 100) if prior_value else None
        comparison.append({
            "name": label,
            "periode": current[key],
            "n_1": prior_value,
            "evolution_pct": evolution,
        })

    alerts = []
    if current["resultat_financier"] < 0:
        alerts.append({
            "level": "danger",
            "title": "Résultat financier déficitaire",
            "message": f"Les charges financières dépassent les produits de {abs(current['resultat_financier']):,.3f} TND.",
        })
    if current["ebitda_pct"] < 0:
        alerts.append({
            "level": "danger",
            "title": "Rentabilité opérationnelle négative",
            "message": f"La marge EBITDA atteint {current['ebitda_pct']:.3f}% sur la période filtrée.",
        })
    if current["resultat_net_pct"] < 0:
        alerts.append({
            "level": "danger",
            "title": "Marge nette négative",
            "message": f"La marge nette atteint {current['resultat_net_pct']:.3f}% sur la période filtrée.",
        })
    if has_previous and previous["charges_financieres"]:
        growth = (current["charges_financieres"] - previous["charges_financieres"]) / abs(previous["charges_financieres"]) * 100
        if growth > 20:
            alerts.append({
                "level": "warning",
                "title": "Hausse des charges financières",
                "message": f"Elles progressent de {growth:.1f}% par rapport à la période N-1.",
            })
    total_analyzed_charges = sum(item["value"] for item in charge_structure)
    if charge_structure and total_analyzed_charges:
        largest = max(charge_structure, key=lambda item: item["value"])
        share = largest["value"] / total_analyzed_charges * 100
        if share >= 40:
            alerts.append({
                "level": "info",
                "title": f"Poids élevé : {largest['name']}",
                "message": f"Ce poste représente {share:.1f}% des charges analysées.",
            })
    if not alerts:
        alerts.append({
            "level": "success",
            "title": "Aucun signal critique",
            "message": "Les principaux indicateurs restent maîtrisés sur la période filtrée.",
        })

    return charge_structure, comparison, alerts


def _get_bfc_stats(cursor, date_debut=None, date_fin=None):
    where_clause, params = _bfc_where(date_debut, date_fin)
    cursor.execute(
        f"SELECT periode, resume FROM sage_bfc_monthly{where_clause} ORDER BY periode ASC",
        params,
    )
    rows = cursor.fetchall()
    nb_periodes = len(rows)

    if nb_periodes == 0:
        return {
            "nb_periodes": 0,
            "tendance": [],
            "premiere_periode": None,
            "derniere_periode": None,
            "pnl_detail": None,
            "pnl_cumule": None,
            "charge_structure": [],
            "comparison_n1": {"available": False, "data": []},
            "alerts": [],
        }

    tendance = []
    derniere_periode = None
    dernier_resume = None

    for row in rows:
        resume = _decode_resume(row['resume'])
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
            "produits_financiers": float(resume.get('produits_financiers', 0)),
            "charges_financieres": float(resume.get('charges_financieres', 0)),
            "resultat_financier": float(resume.get('resultat_financier', 0)),
        })

        derniere_periode = periode_str
        dernier_resume = resume

    resume_cumule = _aggregate_bfc(rows)

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
            "resultat_exceptionnel": float(dernier_resume.get('resultat_exceptionnel', 0)),
            "dotations": float(dernier_resume.get('dotations', 0)),
            "resultat_avant_impot": float(dernier_resume.get('resultat_avant_impot', 0)),
            "impot_societes": float(dernier_resume.get('impot_societes', 0)),
            "resultat_net": float(dernier_resume.get('resultat_net', 0)),
            "resultat_net_pct": float(dernier_resume.get('resultat_net_pct', 0)),
        }

    # ── P&L cumulé (cartes KPI dashboard) ──
    pnl_cumule = resume_cumule

    # Comparaison avec la même plage de mois de l'année précédente.
    if date_debut or date_fin:
        previous_start = _previous_year(date_debut)
        previous_end = _previous_year(date_fin)
    else:
        previous_start = previous_end = None
    previous_rows = []
    if previous_start or previous_end:
        previous_where, previous_params = _bfc_where(previous_start, previous_end)
        cursor.execute(
            f"SELECT periode, resume FROM sage_bfc_monthly{previous_where} ORDER BY periode ASC",
            previous_params,
        )
        previous_rows = cursor.fetchall()
    previous_cumule = _aggregate_bfc(previous_rows)
    charge_structure, comparison, alerts = _build_bfc_decision_data(
        pnl_cumule, previous_cumule, bool(previous_rows)
    )

    return {
        "nb_periodes": nb_periodes,
        "tendance": tendance,
        "premiere_periode": str(rows[0]["periode"])[:7],
        "derniere_periode": derniere_periode,
        "pnl_detail": pnl_detail,
        "pnl_cumule": pnl_cumule,
        "charge_structure": charge_structure,
        "comparison_n1": {
            "available": bool(previous_rows),
            "data": comparison,
        },
        "alerts": alerts,
    }


def _get_latest_bfc_year_kpis(cursor):
    cursor.execute("SELECT MAX(periode) AS latest_periode FROM sage_bfc_monthly")
    latest_row = cursor.fetchone() or {}
    latest_period = latest_row.get("latest_periode")
    if not latest_period:
        return {"year": None, "ca_net": 0.0, "resultat_net": 0.0, "resultat_net_pct": 0.0}

    latest_date = latest_period if isinstance(latest_period, date) else date.fromisoformat(str(latest_period)[:10])
    year_start = date(latest_date.year, 1, 1)
    next_year = date(latest_date.year + 1, 1, 1)
    cursor.execute(
        "SELECT periode, resume FROM sage_bfc_monthly "
        "WHERE periode >= %s AND periode < %s ORDER BY periode ASC",
        [year_start, next_year],
    )
    totals = _aggregate_bfc(cursor.fetchall())
    return {
        "year": latest_date.year,
        "ca_net": totals["ca_net"],
        "resultat_net": totals["resultat_net"],
        "resultat_net_pct": totals["resultat_net_pct"],
    }


def _get_previous_cash_flow(cursor, date_debut, date_fin):
    if not date_debut and not date_fin:
        return None
    where_clause = "WHERE 1=1"
    params = []
    if date_debut:
        where_clause += " AND date_ecriture >= %s"
        params.append(_previous_year(date_debut))
    if date_fin:
        where_clause += " AND date_ecriture <= %s"
        params.append(_previous_year(date_fin))
    cursor.execute(
        f"SELECT COUNT(*) AS row_count, COALESCE(SUM(debit), 0) AS debit, COALESCE(SUM(credit), 0) AS credit "
        f"FROM ecritures_caisse {where_clause}",
        params,
    )
    row = cursor.fetchone() or {}
    if not int(row.get("row_count") or 0):
        return None
    return float(row.get("debit") or 0) - float(row.get("credit") or 0)


def _get_overview_stats(cursor, caisse, migration, bfc, latest_bfc, date_debut, date_fin):
    pending = int(caisse.get("ecritures_en_attente") or 0)
    bfc_periods = int(bfc.get("nb_periodes") or 0)

    alerts = []
    if float(caisse.get("solde_actuel") or 0) < 0:
        alerts.append({"level": "danger", "title": "Solde de caisse négatif", "message": "Le solde actuel nécessite une vérification.", "target_section": "tresorerie"})
    if pending:
        alerts.append({"level": "warning", "title": "Écritures à migrer", "message": f"{pending} écriture(s) attendent la migration vers SAGE.", "target_section": "tresorerie"})
    if not migration.get("equilibre"):
        alerts.append({"level": "danger", "title": "Balance SAGE déséquilibrée", "message": f"Écart constaté : {abs(float(migration.get('difference') or 0)):,.3f} TND.", "target_section": "tresorerie"})
    if int(migration.get("nb_desequilibres") or 0):
        alerts.append({"level": "warning", "title": "Pièces déséquilibrées", "message": f"{migration['nb_desequilibres']} pièce(s) présentent un déséquilibre.", "target_section": "tresorerie"})
    if not bfc_periods:
        alerts.append({"level": "warning", "title": "Analyse BFC indisponible", "message": "Aucune balance BFC n'est disponible pour la période.", "target_section": "bfc"})
    else:
        for alert in bfc.get("alerts", []):
            if alert.get("level") in {"danger", "warning"}:
                alerts.append({**alert, "target_section": "bfc"})
    if not alerts:
        alerts.append({"level": "success", "title": "Situation maîtrisée", "message": "Aucune anomalie prioritaire sur la période filtrée.", "target_section": None})

    current_cash_flow = float(caisse.get("total_debit") or 0) - float(caisse.get("total_credit") or 0)
    previous_cash_flow = _get_previous_cash_flow(cursor, date_debut, date_fin)
    comparison = [{"name": "Flux net", "periode": current_cash_flow, "n_1": previous_cash_flow or 0}]
    bfc_comparison = {item["name"]: item for item in bfc.get("comparison_n1", {}).get("data", [])}
    for name in ("CA Net", "EBITDA", "Résultat net"):
        item = bfc_comparison.get(name)
        if item:
            comparison.append({"name": name, "periode": item["periode"], "n_1": item["n_1"]})
    comparison_available = previous_cash_flow is not None or bool(bfc.get("comparison_n1", {}).get("available"))

    return {
        "kpis": {
            "cash_flow": current_cash_flow,
            "pending_migration": pending,
            "latest_bfc_year": latest_bfc.get("year"),
            "ca_net": float(latest_bfc.get("ca_net") or 0),
            "resultat_net": float(latest_bfc.get("resultat_net") or 0),
            "resultat_net_pct": float(latest_bfc.get("resultat_net_pct") or 0),
        },
        "alerts": alerts,
        "comparison": {"available": comparison_available, "data": comparison},
    }
