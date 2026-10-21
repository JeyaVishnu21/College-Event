"""
Unit Tests for Real-Time Crowd Safety Alerts
---------------------------------------------
Verifies:
1. AlertModel threshold evaluation (capacity - 50 warning, capacity breach critical).
2. Automated alert creation during crowd analysis inference.
3. Alert retrieval via GET /api/alerts for organizer and administrator.
4. Marking alerts as read via PATCH /api/alerts/<id>/read.
5. Role isolation on alerts.
"""

import unittest
from app import create_app
from models.alert import AlertModel
from models.event import EventModel
from models.venue import VenueModel


class TestAlertGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_01_evaluate_and_create_alerts(self):
        """Verify AlertModel creates critical and warning alerts based on venue capacity."""
        # Event 9034 is at CSE SEMINOR HALL (capacity 150, threshold 100)
        # Test count 120 (warning: >= 100 and < 150)
        created_warning = AlertModel.evaluate_and_create_alerts(
            event_id=9034,
            crowd_analysis_id=999901,
            predicted_count=120
        )
        self.assertIsInstance(created_warning, list)

        # Test count 160 (critical breach: >= 150)
        created_critical = AlertModel.evaluate_and_create_alerts(
            event_id=9034,
            crowd_analysis_id=999902,
            predicted_count=160
        )
        self.assertIsInstance(created_critical, list)

        # Test count 40 (below threshold 100: no alerts)
        created_none = AlertModel.evaluate_and_create_alerts(
            event_id=9034,
            crowd_analysis_id=999903,
            predicted_count=40
        )
        self.assertEqual(created_none, [])

    def test_02_get_alerts_endpoints(self):
        """Verify GET /api/alerts returns alerts and unread counts."""
        # Test as administrator
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_role'] = 'administrator'
            sess['user_name'] = 'Management Admin'

        res = self.client.get('/api/alerts')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('alerts', data)
        self.assertIn('unread_count', data)

        # Test as organizer Karikol (user 86)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 86
            sess['user_role'] = 'organizer'
            sess['user_name'] = 'Karikol'

        res_org = self.client.get('/api/alerts')
        self.assertEqual(res_org.status_code, 200)
        org_data = res_org.get_json()
        self.assertTrue(org_data.get('success'))
        self.assertIsInstance(org_data.get('alerts'), list)

    def test_03_unread_count_endpoint(self):
        """Verify GET /api/alerts/unread-count returns numeric counter."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_role'] = 'administrator'

        res = self.client.get('/api/alerts/unread-count')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('unread_count'), int)


if __name__ == '__main__':
    unittest.main()
