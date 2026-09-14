import inspect
import unittest
from datetime import datetime

from modules.notifications.models import NotificationItem
from modules.notifications.router import list_notifications
from modules.notifications.rules import has_important_reconciliation_discrepancy
from modules.notifications.service import get_user_notifications
from modules.notifications import scheduler


class TestNotifications(unittest.TestCase):
    def test_notification_supports_contextual_navigation(self):
        item = NotificationItem(
            id=12,
            user_id=3,
            type="sage_bfc.periode_supprimee",
            module="sage_bfc",
            severity="warning",
            title="Période supprimée",
            message="La période 2026-08 a été supprimée.",
            is_read=True,
            read_at=datetime(2026, 9, 14, 10, 30),
            entity_type="sage_bfc_period",
            entity_id="2026-08",
            route="/sage-bfc?periode=2026-08&section=dashboard",
            created_at=datetime(2026, 9, 14, 10, 0),
        )
        self.assertEqual(item.entity_id, "2026-08")
        self.assertIn("periode=2026-08", item.route)
        self.assertIsNotNone(item.read_at)

    def test_notifications_endpoint_has_no_display_limit(self):
        endpoint_parameters = inspect.signature(list_notifications).parameters
        self.assertNotIn("limit", endpoint_parameters)
        self.assertNotIn("offset", endpoint_parameters)
        self.assertNotIn("unread_only", endpoint_parameters)
        self.assertNotIn("LIMIT ", inspect.getsource(get_user_notifications).upper())
        self.assertNotIn("purge", inspect.getsource(scheduler.start_scheduler).lower())

    def test_reconciliation_alert_thresholds(self):
        self.assertFalse(has_important_reconciliation_discrepancy(4, 999.999))
        self.assertTrue(has_important_reconciliation_discrepancy(5, 0))
        self.assertTrue(has_important_reconciliation_discrepancy(0, -1000))


if __name__ == "__main__":
    unittest.main()
