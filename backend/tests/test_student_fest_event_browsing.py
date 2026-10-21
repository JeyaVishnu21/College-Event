"""
Test Suite: Student/Public Fest-First Event Browsing
---------------------------------------------------
Verifies all 10 acceptance criteria for the Fest-First student browsing workflow:
1. Fests load dynamically with name, dates, status, event_count.
2. Selecting Fest A (e.g., Legacy 2026) returns ONLY Fest A events.
3. Selecting Fest B (e.g., Gyan Mitra 2026) returns ONLY Fest B events.
4. Same event name under different Fests appears separately and correctly isolated.
5. Event search within Fest returns filtered events for that Fest only.
6. Changing Fest clears previous and loads only the new Fest events.
7. Empty Fest handling (0 public events returns empty list cleanly).
8. Empty search result handling.
9. Event details endpoint preserves associated Fest name and metadata.
10. Public visibility: Pending/rejected events are never exposed to public/student.
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


class TestStudentFestEventBrowsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-student-fest-browsing-2026'

        # Always isolate to an in-memory SQLite database
        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.patch_models()

        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Seed test organizer
                pw_hash = hash_password("Organizer@123")
                cur.execute("""
                    INSERT INTO users (id, name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), role = VALUES(role);
                """, (70, "Student Fest Test Org", "student_fest_org@college.edu", pw_hash, "organizer"))

                # Seed test venue
                cur.execute("""
                    INSERT INTO venues (id, name, location, capacity, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), status = VALUES(status);
                """, (70, "Student Browsing Hall", "Block S, 1st Floor", 400, "available"))

                # Seed 3 distinct fests:
                # Fest 901: Legacy 2026 (Has 3 approved events)
                # Fest 902: Gyan Mitra 2026 (Has 2 approved events, including same-named "Paper Presentation")
                # Fest 903: Empty Fest 2026 (Has 0 approved events)
                d1 = (date.today() + timedelta(days=20)).isoformat()
                d2 = (date.today() + timedelta(days=22)).isoformat()
                d3 = (date.today() + timedelta(days=40)).isoformat()
                d4 = (date.today() + timedelta(days=42)).isoformat()
                d5 = (date.today() + timedelta(days=80)).isoformat()
                d6 = (date.today() + timedelta(days=82)).isoformat()

                cur.execute("""
                    INSERT INTO event_series (id, name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);
                """, (901, "Legacy 2026", "Annual Technical Fest", d1, d2))

                cur.execute("""
                    INSERT INTO event_series (id, name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);
                """, (902, "Gyan Mitra 2026", "National Cultural Fest", d3, d4))

                cur.execute("""
                    INSERT INTO event_series (id, name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);
                """, (903, "Empty Fest 2026", "Upcoming Fest with no events yet", d5, d6))

                # Clean prior test events for these series
                cur.execute("DELETE FROM events WHERE series_id IN (901, 902, 903);")

                # Events under Legacy 2026 (901):
                # 1. Paper Presentation (Approved)
                # 2. Project Expo (Approved)
                # 3. Coding Contest (Approved)
                # 4. Pending Hackathon (Pending - must NOT appear in public API)
                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9001, 901, 70, "Paper Presentation", "Technical paper presentations", "Technical", "approved",
                      d1, "09:00:00", "12:00:00", d1, "09:00:00", "12:00:00", 70))

                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9002, 901, 70, "Project Expo", "Working model display", "Technical", "approved",
                      d1, "13:00:00", "16:00:00", d1, "13:00:00", "16:00:00", 70))

                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9003, 901, 70, "Coding Contest", "Competitive programming", "Technical", "approved",
                      d2, "10:00:00", "13:00:00", d2, "10:00:00", "13:00:00", 70))

                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9004, 901, 70, "Pending Hackathon", "Awaiting review", "Technical", "pending",
                      d2, "14:00:00", "18:00:00", 70))

                # Events under Gyan Mitra 2026 (902):
                # 1. Paper Presentation (Approved - Same event name as in Legacy!)
                # 2. Quiz Competition (Approved)
                # 3. Rejected Drama (Rejected - must NOT appear in public API)
                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9005, 902, 70, "Paper Presentation", "Cultural symposium research paper", "Cultural", "approved",
                      d3, "10:00:00", "13:00:00", d3, "10:00:00", "13:00:00", 70))

                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9006, 902, 70, "Quiz Competition", "General & pop culture quiz", "Cultural", "approved",
                      d4, "11:00:00", "14:00:00", d4, "11:00:00", "14:00:00", 70))

                cur.execute("""
                    INSERT INTO events (id, series_id, organizer_id, event_name, description, category, status, rejection_reason,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (9007, 902, 70, "Rejected Drama", "Drama event rejected", "Cultural", "rejected", "Policy restriction",
                      d4, "15:00:00", "18:00:00", 70))

            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'isolated_db'):
            cls.isolated_db.restore_models()

    def setUp(self):
        self.client = self.app.test_client()

    def test_01_public_fests_load_dynamically(self):
        """1. Verify Fests load dynamically with required metadata (name, dates, status, count)."""
        res = self.client.get('/api/public/event-series')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        series = data.get("series", [])
        self.assertGreaterEqual(len(series), 3)

        # Check Legacy 2026
        legacy = next((s for s in series if s["id"] == 901), None)
        self.assertIsNotNone(legacy)
        self.assertEqual(legacy["name"], "Legacy 2026")
        self.assertIn("start_date", legacy)
        self.assertIn("end_date", legacy)
        self.assertIn("status", legacy)
        # Should count exactly the 3 approved events (excludes pending 9004)
        self.assertEqual(legacy["event_count"], 3)

        # Check Gyan Mitra 2026
        gyan = next((s for s in series if s["id"] == 902), None)
        self.assertIsNotNone(gyan)
        self.assertEqual(gyan["name"], "Gyan Mitra 2026")
        # Should count exactly the 2 approved events (excludes rejected 9007)
        self.assertEqual(gyan["event_count"], 2)

    def test_02_select_legacy_displays_only_legacy_events(self):
        """2. Select Legacy and verify only Legacy events appear (does NOT leak Gyan Mitra)."""
        res = self.client.get('/api/public/events?series_id=901')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        events = data.get("events", [])
        self.assertEqual(len(events), 3)

        event_names = [e["event_name"] for e in events]
        self.assertIn("Paper Presentation", event_names)
        self.assertIn("Project Expo", event_names)
        self.assertIn("Coding Contest", event_names)

        # Must NOT include Gyan Mitra's Quiz
        self.assertNotIn("Quiz Competition", event_names)

        # Verify all events have series_id=901 and series_name='Legacy 2026'
        for e in events:
            self.assertEqual(e["series_id"], 901)
            self.assertEqual(e["series_name"], "Legacy 2026")

    def test_03_select_gyan_mitra_displays_only_gyan_mitra_events(self):
        """3. Select Gyan Mitra and verify only Gyan Mitra events appear."""
        res = self.client.get('/api/public/events?series_id=902')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        events = data.get("events", [])
        self.assertEqual(len(events), 2)

        event_names = [e["event_name"] for e in events]
        self.assertIn("Paper Presentation", event_names)
        self.assertIn("Quiz Competition", event_names)

        # Must NOT include Legacy's Coding Contest or Project Expo
        self.assertNotIn("Coding Contest", event_names)
        self.assertNotIn("Project Expo", event_names)

        for e in events:
            self.assertEqual(e["series_id"], 902)
            self.assertEqual(e["series_name"], "Gyan Mitra 2026")

    def test_04_same_event_name_under_different_fests(self):
        """4. Verify same event name ('Paper Presentation') appears separately under different Fests."""
        res_legacy = self.client.get('/api/public/events?series_id=901&search=Paper')
        res_gyan = self.client.get('/api/public/events?series_id=902&search=Paper')

        ev_legacy = res_legacy.get_json()["events"][0]
        ev_gyan = res_gyan.get_json()["events"][0]

        # Both have event_name 'Paper Presentation'
        self.assertEqual(ev_legacy["event_name"], "Paper Presentation")
        self.assertEqual(ev_gyan["event_name"], "Paper Presentation")

        # But different event IDs and different series
        self.assertNotEqual(ev_legacy["id"], ev_gyan["id"])
        self.assertEqual(ev_legacy["series_id"], 901)
        self.assertEqual(ev_legacy["series_name"], "Legacy 2026")
        self.assertEqual(ev_legacy["category"], "Technical")

        self.assertEqual(ev_gyan["series_id"], 902)
        self.assertEqual(ev_gyan["series_name"], "Gyan Mitra 2026")
        self.assertEqual(ev_gyan["category"], "Cultural")

    def test_05_search_event_within_fest(self):
        """5. Verify event search within selected Fest isolates to that Fest."""
        # Search "Paper" under Legacy (901)
        res = self.client.get('/api/public/events?series_id=901&search=Paper')
        events = res.get_json()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], 9001)
        self.assertEqual(events[0]["series_name"], "Legacy 2026")

        # Search "Coding" under Legacy (901)
        res2 = self.client.get('/api/public/events?series_id=901&search=Coding')
        events2 = res2.get_json()["events"]
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0]["event_name"], "Coding Contest")

        # Search "Coding" under Gyan Mitra (902) -> 0 results
        res3 = self.client.get('/api/public/events?series_id=902&search=Coding')
        events3 = res3.get_json()["events"]
        self.assertEqual(len(events3), 0)

    def test_06_empty_fest_handling(self):
        """6. Verify empty Fest handling (Fest 903 with 0 events returns empty list cleanly)."""
        res = self.client.get('/api/public/events?series_id=903')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("events"), [])
        self.assertEqual(data.get("count"), 0)

    def test_07_public_visibility_does_not_expose_pending_or_rejected(self):
        """7. Verify pending (9004) and rejected (9007) events are NEVER publicly visible."""
        res_legacy = self.client.get('/api/public/events?series_id=901')
        legacy_ids = [e["id"] for e in res_legacy.get_json()["events"]]
        self.assertNotIn(9004, legacy_ids)  # Pending hackathon

        res_gyan = self.client.get('/api/public/events?series_id=902')
        gyan_ids = [e["id"] for e in res_gyan.get_json()["events"]]
        self.assertNotIn(9007, gyan_ids)  # Rejected drama

    def test_08_event_details_displays_associated_fest(self):
        """8. Verify single event details endpoint preserves fest series metadata."""
        res = self.client.get('/api/public/events/9001')
        self.assertEqual(res.status_code, 200)
        ev = res.get_json()["event"]
        self.assertEqual(ev["event_name"], "Paper Presentation")
        self.assertEqual(ev["series_id"], 901)
        self.assertEqual(ev["series_name"], "Legacy 2026")
        self.assertIn("Technical Fest", ev["series_description"])


if __name__ == '__main__':
    unittest.main()
