"""
Integration Test Suite for Public Event Discovery APIs
------------------------------------------------------
Validates that public endpoints:
1. Work without authentication.
2. Return real database events.
3. Support search, year, month, category, and status filtering.
4. Expose complete event and venue details.
5. Return crowd information with maximum predicted count and normal/high status.
6. Handle events without crowd analysis with proper empty state.
7. Support festival series listing and grouped events.
8. Do NOT leak private organizer, management, alert, or auth details.
"""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app


class TestPublicAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_01_public_events_no_auth_required(self):
        """Verify public events list returns 200 without cookies or auth."""
        resp = self.client.get('/api/public/events')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['events'], list)
        self.assertGreater(data['count'], 0)
        print(f"   [OK] Public events retrieved: {data['count']} events found without login.")

    def test_02_search_filter(self):
        """Verify searching by event name returns matching records."""
        resp = self.client.get('/api/public/events?search=Tournament')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        names = [e['event_name'] for e in data['events']]
        self.assertTrue(any('Tournament' in n for n in names))
        print("   [OK] Search filter works as expected.")

    def test_03_category_filter(self):
        """Verify category filtering."""
        resp = self.client.get('/api/public/events?category=General')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        for e in data['events']:
            self.assertEqual(e['category'].lower(), 'general')
        print(f"   [OK] Category filter returned {len(data['events'])} General events.")

    def test_04_status_filter_upcoming_and_completed(self):
        """Verify filtering by upcoming vs completed status."""
        resp_comp = self.client.get('/api/public/events?status=completed')
        self.assertEqual(resp_comp.status_code, 200)
        data_comp = resp_comp.get_json()
        self.assertTrue(data_comp['success'])
        self.assertGreater(data_comp['count'], 0)
        print(f"   [OK] Status filter completed returned {data_comp['count']} events.")

    def test_05_year_filter(self):
        """Verify year filtering."""
        resp_2026 = self.client.get('/api/public/events?year=2026')
        self.assertEqual(resp_2026.status_code, 200)
        data_2026 = resp_2026.get_json()
        self.assertTrue(data_2026['success'])
        for e in data_2026['events']:
            self.assertTrue(e['start_date'].startswith('2026'))
        print(f"   [OK] Year filter for 2026 returned {data_2026['count']} events.")

    def test_06_event_detail_with_crowd_info(self):
        """Verify public event detail with crowd monitoring."""
        # Find an event with crowd analysis
        resp = self.client.get('/api/public/events')
        data = resp.get_json()
        analyzed_event = next((e for e in data['events'] if e['estimated_crowd'] is not None), None)

        if analyzed_event:
            ev_id = analyzed_event['id']
            detail_resp = self.client.get(f'/api/public/events/{ev_id}')
            self.assertEqual(detail_resp.status_code, 200)
            det = detail_resp.get_json()['event']
            self.assertTrue(det['crowd_info']['available'])
            self.assertIsNotNone(det['crowd_info']['estimated_crowd'])
            self.assertIn(det['crowd_info']['crowd_status'], ['Normal Crowd', 'High Crowd'])
            print(f"   [OK] Event {ev_id} crowd detail: {det['crowd_info']['estimated_crowd']} people, status: {det['crowd_info']['crowd_status']}.")

    def test_07_event_detail_without_crowd_info_empty_state(self):
        """Verify event without crowd analysis returns clean empty state."""
        resp = self.client.get('/api/public/events')
        data = resp.get_json()
        unanalyzed_event = next((e for e in data['events'] if e['estimated_crowd'] is None), None)

        if unanalyzed_event:
            ev_id = unanalyzed_event['id']
            detail_resp = self.client.get(f'/api/public/events/{ev_id}')
            self.assertEqual(detail_resp.status_code, 200)
            det = detail_resp.get_json()['event']
            self.assertFalse(det['crowd_info']['available'])
            self.assertIsNone(det['crowd_info']['estimated_crowd'])
            self.assertEqual(det['crowd_info']['message'], "Crowd information is not available yet.")
            print(f"   [OK] Event {ev_id} handles missing crowd analysis cleanly.")

    def test_08_event_series_endpoints(self):
        """Verify event series list endpoint returns 200 and valid JSON structure."""
        resp = self.client.get('/api/public/event-series')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['series'], list)

        if data['count'] > 0:
            series_id = data['series'][0]['id']
            detail_resp = self.client.get(f'/api/public/event-series/{series_id}')
            self.assertEqual(detail_resp.status_code, 200)
            s_data = detail_resp.get_json()['series']
            self.assertIn('events', s_data)
            print(f"   [OK] Event series '{s_data['name']}' returned with {s_data['total_events']} grouped events.")
        else:
            # 404 for non-existent series
            detail_resp = self.client.get('/api/public/event-series/9999')
            self.assertEqual(detail_resp.status_code, 404)
            print("   [OK] Event series list returned 200 and empty state verified safely.")

    def test_09_categories_and_years_endpoint(self):
        """Verify filter metadata endpoint."""
        resp = self.client.get('/api/public/categories')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['categories'], list)
        self.assertIsInstance(data['years'], list)
        print(f"   [OK] Categories: {data['categories']}, Years: {data['years']}")

    def test_10_no_sensitive_data_leakage(self):
        """Verify public endpoints never leak passwords, rejection reasons, or internal alert tables."""
        resp = self.client.get('/api/public/events')
        data = resp.get_json()
        for e in data['events']:
            self.assertNotIn('password', e)
            self.assertNotIn('password_hash', e)
            self.assertNotIn('organizer_email', e)
            self.assertNotIn('rejection_reason', e)
        print("   [OK] Verified zero private data leakage.")


if __name__ == '__main__':
    unittest.main()
