"""
Tâches planifiées pour les notifications OLEA.

- Rappels périodiques : données forecast manquantes, mois Sage BFC manquants
"""

import asyncio
from datetime import date

from database import db
REMINDER_INTERVAL = 6 * 3600  # 6h


async def _reminder_loop():
    """Vérifie les rappels périodiques (mois Sage BFC manquants)."""
    # Exécuter un premier check au démarrage après une courte attente
    await asyncio.sleep(5)
    _run_reminder_checks("initial")

    while True:
        await asyncio.sleep(REMINDER_INTERVAL)
        _run_reminder_checks("périodique")


def _run_reminder_checks(context: str):
    """Isole les contrôles pour qu'une panne d'un module ne bloque pas les autres."""
    for name, check in (
        ("SAGE → BFC", _check_sage_bfc_missing_months),
        ("sessions bancaires", _check_pending_bank_sessions),
    ):
        try:
            check()
        except Exception as exc:
            print(f"⚠️ Erreur rappel {name} ({context}) : {exc}")


def _check_sage_bfc_missing_months():
    """Vérifie s'il y a des trous dans la séquence des mois Sage BFC."""
    today = date.today()
    current_year = today.year
    current_month = today.month

    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT MONTH(periode) AS m FROM sage_bfc_monthly "
            "WHERE YEAR(periode) = %s ORDER BY m",
            (current_year,),
        )
        existing_months = {row["m"] for row in cursor.fetchall()}

    if not existing_months:
        return

    max_month = max(existing_months)
    expected = set(range(1, max_month + 1))
    missing = sorted(expected - existing_months)

    if missing and missing != list(range(max_month, current_month + 1)):
        month_names = [
            "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]
        missing_labels = [month_names[m] for m in missing if m < len(month_names)]
        from .service import create_notification, _get_users_for_module
        user_ids = _get_users_for_module("sage_bfc")
        create_notification(
            user_ids=user_ids,
            notif_type="sage_bfc.mois_manquant",
            module="sage_bfc",
            severity="critical",
            title="Mois manquants dans Sage BFC",
            message=f"Les mois suivants sont absents pour {current_year} : {', '.join(missing_labels)}.",
            metadata={"year": current_year, "missing_months": missing},
            dedup_minutes=360,  # 6h — évite les doublons entre exécutions du scheduler
            entity_type="sage_bfc_year",
            entity_id=str(current_year),
            route=f"/sage-bfc?year={current_year}&section=upload",
        )


def _check_pending_bank_sessions():
    """Rappelle au créateur les sessions bancaires inachevées depuis au moins une heure."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id, created_by_user_id, compte_banque, file_name, updated_at "
            "FROM bank_reconciliation_batches "
            "WHERE status IN ('extracted', 'in_progress') "
            "AND updated_at < NOW() - INTERVAL 1 HOUR"
        )
        sessions = cursor.fetchall() or []

    from .service import create_notification, _get_users_for_module
    fallback_users = None
    for session in sessions:
        recipient = session.get("created_by_user_id")
        if recipient:
            user_ids = [int(recipient)]
        else:
            if fallback_users is None:
                fallback_users = _get_users_for_module("saisie_bancaire")
            user_ids = fallback_users
        create_notification(
            user_ids=user_ids,
            notif_type="saisie_bancaire.session_non_finalisee",
            module="saisie_bancaire",
            severity="warning",
            title="Session bancaire non finalisée",
            message=f"La session {session['file_name']} ({session['compte_banque']}) attend d'être finalisée.",
            metadata={"batch_id": session["id"], "file_name": session["file_name"]},
            dedup_minutes=360,
            entity_type="bank_session",
            entity_id=str(session["id"]),
            route=f"/saisie-bancaire?session={session['id']}",
        )


async def start_scheduler():
    """Démarre les tâches planifiées en arrière-plan."""
    asyncio.create_task(_reminder_loop())
