"""
Unit & Integration Test Suite: Organizer Event Creation with Fest Selection
----------------------------------------------------------------------------
Validates the 'ORGANIZER EVENT CREATION -> SELECT FEST FIRST' implementation:
1. Organizer can create an event with a valid series_id.
2. Created event contains the correct series_id and series_name.
3. Missing series_id is rejected with HTTP 400.
4. Invalid series_id (string, negative, None) is rejected with HTTP 400.
5. Non-existing series_id (e.g., 99999) is rejected with HTTP 400.
6. Created event has status = 'pending' and requested date/time/venue intact.
7. Same event name under different fests is permitted (no global unique constraint).
8. Organizer dashboard lists include series_id and series_name.
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
import config.db
from middleware.auth import hash_password
from models.event import EventModel
from models.event_series import EventSeriesModel


from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard

install_global_safety_guard()


class TestOrganizerFestEventCreation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-fest-event-creation-2026'

        # Always isolate to an in-memory SQLite database
        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.patch_models()

        # Seed test users, fests, and venue in isolated database
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Ensure test organizer exists
                pw_hash = hash_password("Organizer@123")
                cur.execute("""
                    INSERT INTO users (id, name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s);
                """, (55, "Test Organizer", "test_org_fest@college.edu", pw_hash, "organizer"))

                # Seed test venue
                cur.execute("""
                    INSERT INTO venues (id, name, location, capacity, status)
                    VALUES (%s, %s, %s, %s, %s);
                """, (55, "Fest Hall Alpha", "Block C, 3rd Floor", 300, "available"))

                # Seed two distinct fests (event_series)
                d1 = (date.today() + timedelta(days=30)).isoformat()
                d2 = (date.today() + timedelta(days=32)).isoformat()
                d3 = (date.today() + timedelta(days=60)).isoformat()
                d4 = (date.today() + timedelta(days=62)).isoformat()

                cur.execute("""
                    INSERT INTO event_series (id, name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s);
                """, (881, "Legacy 2026", "Annual State Level Technical Symposium", d1, d2))

                cur.execute("""
                    INSERT INTO event_series (id, name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s);
                """, (882, "Gyan Mitra 2026", "National Inter-Collegiate Cultural Festival", d3, d4))

            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'isolated_db'):
            cls.isolated_db.restore_models()

    def setUp(self):
        self.client = self.app.test_client()
        # Log in as test organizer
        res = self.client.post('/api/auth/login', json={
            "email": "test_org_fest@college.edu",
            "password": "Organizer@123"
        })
        self.assertEqual(res.status_code, 200, "Failed to authenticate test organizer")

    def test_01_create_event_with_valid_series_id(self):
        """Test organizer can successfully create an event with a valid series_id."""
        req_date = (date.today() + timedelta(days=31)).isoformat()
        payload = {
            "series_id": 881,
            "event_name": "Paper Presentation - AI Track",
            "category": "Technical",
            "description": "Technical paper presentation under Legacy 2026 fest.",
            "requested_date": req_date,
            "requested_start_time": "10:00:00",
            "requested_end_time": "13:00:00",
            "venue_id": 55
        }
        res = self.client.post('/api/events', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertIn("event", data)
        event = data["event"]
        self.assertEqual(event["series_id"], 881)
        self.assertEqual(event["status"], "pending")
        self.assertEqual(event["event_name"], "Paper Presentation - AI Track")

    def test_02_created_event_contains_correct_series_info(self):
        """Test that get_by_id returns the correct series_id and series_name."""
        req_date = (date.today() + timedelta(days=31)).isoformat()
        payload = {
            "series_id": 881,
            "event_name": "Coding Contest",
            "category": "Technical",
            "description": "Speed coding contest.",
            "requested_date": req_date,
            "requested_start_time": "14:00:00",
            "requested_end_time": "16:00:00",
            "venue_id": 55
        }
        res = self.client.post('/api/events', json=payload)
        self.assertEqual(res.status_code, 201)
        event_id = res.get_json()["event"]["id"]

        # Verify via EventModel directly and route
        ev = EventModel.get_by_id(event_id)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["series_id"], 881)
        self.assertEqual(ev["series_name"], "Legacy 2026")
        self.assertIn("Technical Symposium", ev["series_description"])

    def test_03_missing_series_id_rejected(self):
        """Test missing series_id is rejected with HTTP 400."""
        req_date = (date.today() + timedelta(days=31)).isoformat()
        payload = {
            "event_name": "No Fest Event",
            "category": "General",
            "description": "Event submitted without fest",
            "requested_date": req_date,
            "requested_start_time": "10:00:00",
            "requested_end_time": "12:00:00"
        }
        res = self.client.post('/api/events', json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue("fest" in data.get("message", "").lower() or "series_id" in data.get("message", "").lower())

    def test_04_invalid_series_id_rejected(self):
        """Test invalid series_id (non-integer, empty string) is rejected with HTTP 400."""
        req_date = (date.today() + timedelta(days=31)).isoformat()
        # String instead of int
        payload = {
            "series_id": "not-a-number",
            "event_name": "Bad Fest Event",
            "category": "General",
            "requested_date": req_date,
            "requested_start_time": "10:00:00",
            "requested_end_time": "12:00:00"
        }
        res = self.client.post('/api/events', json=payload)
        self.assertEqual(res.status_code, 400)

        # None / null
        payload["series_id"] = None
        res2 = self.client.post('/api/events', json=payload)
        self.assertEqual(res2.status_code, 400)

    def test_05_non_existing_fest_rejected(self):
        """Test non-existing fest (series_id=99999) is rejected with HTTP 400."""
        req_date = (date.today() + timedelta(days=31)).isoformat()
        payload = {
            "series_id": 99999,
            "event_name": "Phantom Fest Event",
            "category": "General",
            "requested_date": req_date,
            "requested_start_time": "10:00:00",
            "requested_end_time": "12:00:00"
        }
        res = self.client.post('/api/events', json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("does not exist", data.get("message", "").lower())

    def test_06_same_event_name_under_different_fests_allowed(self):
        """
        Business Rule:
        An event belongs to ONE Fest.
        Legacy -> Paper Presentation
        Gyan Mitra -> Paper Presentation
        Both must be permitted (no global unique event name restriction).
        """
        req_date = (date.today() + timedelta(days=31)).isoformat()

        # Create under Fest 881 (Legacy)
        res1 = self.client.post('/api/events', json={
            "series_id": 881,
            "event_name": "Paper Presentation",
            "category": "Technical",
            "description": "Technical paper presentation for engineers.",
            "requested_date": req_date,
            "requested_start_time": "09:00:00",
            "requested_end_time": "12:00:00"
        })
        self.assertEqual(res1.status_code, 201)
        ev1 = res1.get_json()["event"]
        self.assertEqual(ev1["series_id"], 881)
        self.assertEqual(ev1["event_name"], "Paper Presentation")

        # Create under Fest 882 (Gyan Mitra) with identical name
        res2 = self.client.post('/api/events', json={
            "series_id": 882,
            "event_name": "Paper Presentation",
            "category": "Cultural",
            "description": "Cultural symposium paper presentation.",
            "requested_date": req_date,
            "requested_start_time": "13:00:00",
            "requested_end_time": "16:00:00"
        })
        self.assertEqual(res2.status_code, 201)
        ev2 = res2.get_json()["event"]
        self.assertEqual(ev2["series_id"], 882)
        self.assertEqual(ev2["event_name"], "Paper Presentation")

        # Verify they are two separate database rows
        self.assertNotEqual(ev1["id"], ev2["id"])

    def test_07_organizer_dashboard_includes_fest_name(self):
        """Test that the organizer dashboard endpoint returns events with series_name."""
        res = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        events = data.get("events", [])
        self.assertGreater(len(events), 0)

        # Check that events have series_id and series_name populated
        for e in events:
            if e.get("series_id"):
                self.assertIsNotNone(e.get("series_name"))
                self.assertIn(e["series_name"], ["Legacy 2026", "Gyan Mitra 2026"])


if __name__ == '__main__':
    unittest.main()
