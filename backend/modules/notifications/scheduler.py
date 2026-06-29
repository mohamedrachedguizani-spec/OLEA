"""
Tâches planifiées pour les notifications OLEA.

- Purge automatique des notifications > 30 jours
- Rappels périodiques : données forecast manquantes, mois Sage BFC manquants
"""

import asyncio
from datetime import date

from database import db
from .service import purge_old_notifications


PURGE_INTERVAL = 24 * 3600  # 24h
REMINDER_INTERVAL = 6 * 3600  # 6h


async def _purge_loop():
    """Supprime les notifications de plus de 30 jours, toutes les 24h."""
    while True:
        try:
            deleted = purge_old_notifications(30)
            if deleted:
                print(f"🔔 Purge notifications : {deleted} supprimées (>30 jours)")
        except Exception as e:
            print(f"⚠️ Erreur purge notifications : {e}")
        await asyncio.sleep(PURGE_INTERVAL)


async def _reminder_loop():
    """Vérifie les rappels périodiques (mois Sage BFC manquants)."""
    # Exécuter un premier check au démarrage après une courte attente
    await asyncio.sleep(5)
    try:
        _check_sage_bfc_missing_months()
    except Exception as e:
        print(f"⚠️ Erreur rappels notifications initial : {e}")

    while True:
        await asyncio.sleep(REMINDER_INTERVAL)
        try:
            _check_sage_bfc_missing_months()
        except Exception as e:
            print(f"⚠️ Erreur rappels notifications : {e}")


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
        )


async def start_scheduler():
    """Démarre les tâches planifiées en arrière-plan."""
    asyncio.create_task(_purge_loop())
    asyncio.create_task(_reminder_loop())
