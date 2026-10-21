"""
Unit & Integration Tests for Event-Time-Based Photo Upload Restrictions
----------------------------------------------------------------------
Validates all required timing and schedule scenarios:
1.  Immediately before start time (blocked, HTTP 400)
2.  Exactly at start time (permitted, HTTP 201)
3.  During event (permitted, HTTP 201)
4.  Exactly at end time (blocked, HTTP 400)
5.  After end time (blocked, HTTP 400)
6.  On a different date in future (blocked, HTTP 400)
7.  On a different date in past (blocked, HTTP 400)
8.  After management schedule change (dynamically permitted when rescheduled to now, blocked when moved away)
9.  Final approved schedule priority: changes to requested_* fields do not affect approved schedule
10. Unapproved events: pending, rejected, cancelled (blocked, HTTP 400)
11. Event owned by another organizer (blocked, HTTP 403 Forbidden)
12. Read-only image retrieval and crowd analysis review after event has concluded (HTTP 200 OK)
13. Missing or invalid schedules safely handled by denying uploads (HTTP 400)
14. Model unit testing for is_event_happening across edge-case datetimes with timezones
"""

import os
import io
import sys
import shutil
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.settings import settings
import config.db
from middleware.auth import hash_password
from models.event import EventModel
from models.image import ImageModel

try:
    from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
except ImportError:
    from db_guard import IsolatedTestDatabase, install_global_safety_guard


def create_test_jpeg():
    buf = io.BytesIO()
    img = Image.new('RGB', (100, 100), color=(120, 180, 240))
    # Draw non-uniform pixels
    for x in range(20, 80):
        img.putpixel((x, x), (255, 0, 0))
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf


class TestEventTimeUploadRestrictions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_global_safety_guard()
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-upload-timing-secret-2026'

        cls.test_upload_dir = BACKEND_DIR / 'uploads' / 'test_timing_images'
        os.makedirs(cls.test_upload_dir, exist_ok=True)
        cls.orig_upload_folder = settings.UPLOAD_FOLDER
        settings.UPLOAD_FOLDER = cls.test_upload_dir

        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.patch_models()
        cls.seed_db()

    @classmethod
    def tearDownClass(cls):
        settings.UPLOAD_FOLDER = cls.orig_upload_folder
        if os.path.exists(cls.test_upload_dir):
            shutil.rmtree(cls.test_upload_dir, ignore_errors=True)
        cls.isolated_db.restore_models()

    @classmethod
    def seed_db(cls):
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM crowd_analyses;")
                cur.execute("DELETE FROM images;")
                cur.execute("DELETE FROM events;")
                cur.execute("DELETE FROM venues;")
                cur.execute("DELETE FROM users;")

                pw = hash_password("Secret123!")
                cur.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s);",
                            (1, "Management Admin", "admin@college.edu", pw, "management"))
                cur.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s);",
                            (2, "Organizer Alice", "alice@test.edu", pw, "organizer"))
                cur.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s);",
                            (3, "Organizer Bob", "bob@test.edu", pw, "organizer"))

                cur.execute("INSERT INTO venues (id, name, location, capacity, status) VALUES (%s, %s, %s, %s, %s);",
                            (10, "Auditorium", "Campus Center", 500, "available"))
        finally:
            conn.close()

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email="alice@test.edu", password="Secret123!"):
        res = self.client.post('/api/auth/login', json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200)

    def _logout(self):
        self.client.post('/api/auth/logout')

    def _set_event(self, event_id, organizer_id=2, status="approved",
                   req_date="2026-10-20", req_start="09:00:00", req_end="17:00:00",
                   app_date="2026-10-20", app_start="10:00:00", app_end="16:00:00"):
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM events WHERE id = %s;", (event_id,))
                cur.execute("""
                    INSERT INTO events (id, organizer_id, venue_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time)
                    VALUES (%s, %s, 10, %s, 'Test description', %s, %s, %s, %s, %s, %s, %s);
                """, (event_id, organizer_id, f"Event {event_id}", status,
                      req_date, req_start, req_end,
                      app_date, app_start, app_end))
        finally:
            conn.close()

    # =========================================================================
    # 1. Model Unit Tests: Boundary Conditions for is_event_happening
    # =========================================================================

    def test_model_unit_timing_boundaries(self):
        """Validates is_event_happening directly against exact boundary timestamps."""
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        test_date = date(2026, 10, 20)

        event = {
            'status': 'approved',
            'approved_date': test_date,
            'approved_start_time': '14:00:00',
            'approved_end_time': '16:00:00',
        }

        # Case 1: Immediately before start time (13:59:59) -> Blocked
        dt_before = datetime(2026, 10, 20, 13, 59, 59, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_before)
        self.assertFalse(happening)
        self.assertIn("starts today at 14:00:00", reason)

        # Case 2: Exactly at start time (14:00:00) -> Permitted
        dt_start = datetime(2026, 10, 20, 14, 0, 0, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_start)
        self.assertTrue(happening)
        self.assertIn("actively happening live", reason)

        # Case 3: During event (15:30:00) -> Permitted
        dt_mid = datetime(2026, 10, 20, 15, 30, 0, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_mid)
        self.assertTrue(happening)

        # Case 4: Exactly at end time (16:00:00) -> Blocked
        dt_end = datetime(2026, 10, 20, 16, 0, 0, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_end)
        self.assertFalse(happening)
        self.assertIn("concluded today at 16:00:00", reason)

        # Case 5: After end time (16:00:01) -> Blocked
        dt_after = datetime(2026, 10, 20, 16, 0, 1, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_after)
        self.assertFalse(happening)
        self.assertIn("concluded today at 16:00:00", reason)

        # Case 6: Different date in future (tomorrow) -> Blocked
        dt_future_date = datetime(2026, 10, 19, 15, 0, 0, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_future_date)
        self.assertFalse(happening)
        self.assertIn("Uploads open on the event date", reason)

        # Case 7: Different date in past (yesterday) -> Blocked
        dt_past_date = datetime(2026, 10, 21, 15, 0, 0, tzinfo=tz_ist)
        happening, reason = EventModel.is_event_happening(event, current_datetime=dt_past_date)
        self.assertFalse(happening)
        self.assertIn("concluded on 2026-10-20", reason)

    # =========================================================================
    # 2. Integration Tests: Upload API Enforcement
    # =========================================================================

    def test_upload_immediately_before_start_time_is_blocked(self):
        """Immediately before the start time, uploads return HTTP 400 Bad Request."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 13, 59, 59, tzinfo=tz_ist)

        self._set_event(201, organizer_id=2, status="approved",
                        app_date="2026-10-20", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res = self.client.post('/api/events/201/images',
                                   data={'image': (create_test_jpeg(), 'before_start.jpg')},
                                   content_type='multipart/form-data')

            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertIn("starts today at 14:00:00", data.get("message", ""))
        self._logout()

    def test_upload_exactly_at_start_time_is_permitted(self):
        """At exactly the start time (start_time <= current_time), uploads return HTTP 201."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 14, 0, 0, tzinfo=tz_ist)

        self._set_event(202, organizer_id=2, status="approved",
                        app_date="2026-10-20", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res = self.client.post('/api/events/202/images',
                                   data={'image': (create_test_jpeg(), 'at_start.jpg')},
                                   content_type='multipart/form-data')

            self.assertEqual(res.status_code, 201)
            data = res.get_json()
            self.assertTrue(data.get("success"))
        self._logout()

    def test_upload_during_event_is_permitted(self):
        """While the event is in progress, uploads return HTTP 201."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 16, 30, 0, tzinfo=tz_ist)

        self._set_event(203, organizer_id=2, status="approved",
                        app_date="2026-10-20", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res = self.client.post('/api/events/203/images',
                                   data={'image': (create_test_jpeg(), 'during_event.jpg')},
                                   content_type='multipart/form-data')

            self.assertEqual(res.status_code, 201)
        self._logout()

    def test_upload_exactly_at_end_time_is_blocked(self):
        """At exactly the end time (current_time >= end_time), uploads are blocked with HTTP 400."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 18, 0, 0, tzinfo=tz_ist)

        self._set_event(204, organizer_id=2, status="approved",
                        app_date="2026-10-20", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res = self.client.post('/api/events/204/images',
                                   data={'image': (create_test_jpeg(), 'at_end.jpg')},
                                   content_type='multipart/form-data')

            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertIn("concluded today at 18:00:00", data.get("message", ""))
        self._logout()

    def test_upload_after_end_time_is_blocked(self):
        """After the end time has passed, uploads are blocked with HTTP 400."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 18, 30, 0, tzinfo=tz_ist)

        self._set_event(205, organizer_id=2, status="approved",
                        app_date="2026-10-20", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res = self.client.post('/api/events/205/images',
                                   data={'image': (create_test_jpeg(), 'after_end.jpg')},
                                   content_type='multipart/form-data')

            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertIn("concluded today at 18:00:00", data.get("message", ""))
        self._logout()

    def test_upload_on_different_date_future_and_past(self):
        """Uploads on any date other than approved_date are blocked with HTTP 400."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 15, 0, 0, tzinfo=tz_ist)

        # Future event (tomorrow)
        self._set_event(206, organizer_id=2, status="approved",
                        app_date="2026-10-21", app_start="14:00:00", app_end="18:00:00")
        # Past event (yesterday)
        self._set_event(207, organizer_id=2, status="approved",
                        app_date="2026-10-19", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res_future = self.client.post('/api/events/206/images',
                                          data={'image': (create_test_jpeg(), 'future.jpg')},
                                          content_type='multipart/form-data')
            self.assertEqual(res_future.status_code, 400)
            self.assertIn("scheduled for 2026-10-21", res_future.get_json()["message"])

            res_past = self.client.post('/api/events/207/images',
                                        data={'image': (create_test_jpeg(), 'past.jpg')},
                                        content_type='multipart/form-data')
            self.assertEqual(res_past.status_code, 400)
            self.assertIn("concluded on 2026-10-19", res_past.get_json()["message"])

        self._logout()

    def test_upload_reflects_management_schedule_changes(self):
        """When college management updates the approved schedule, upload permission reacts immediately."""
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 15, 0, 0, tzinfo=tz_ist)

        # 1. Initially scheduled for next week -> blocked
        self._set_event(208, organizer_id=2, status="approved",
                        app_date="2026-10-27", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res1 = self.client.post('/api/events/208/images',
                                    data={'image': (create_test_jpeg(), 'reschedule_test.jpg')},
                                    content_type='multipart/form-data')
            self.assertEqual(res1.status_code, 400)

            # 2. Management changes schedule to today 14:00 - 18:00
            conn = config.db.get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE events
                        SET approved_date = '2026-10-20', approved_start_time = '14:00:00', approved_end_time = '18:00:00'
                        WHERE id = 208;
                    """)
            finally:
                conn.close()

            # Now upload should succeed (HTTP 201)
            res2 = self.client.post('/api/events/208/images',
                                    data={'image': (create_test_jpeg(), 'reschedule_test2.jpg')},
                                    content_type='multipart/form-data')
            self.assertEqual(res2.status_code, 201)

            # 3. Management concludes the event early by setting approved_end_time to 14:30:00
            conn = config.db.get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE events
                        SET approved_end_time = '14:30:00'
                        WHERE id = 208;
                    """)
            finally:
                conn.close()

            # Now upload should be blocked again (HTTP 400)
            res3 = self.client.post('/api/events/208/images',
                                    data={'image': (create_test_jpeg(), 'reschedule_test3.jpg')},
                                    content_type='multipart/form-data')
            self.assertEqual(res3.status_code, 400)
            self.assertIn("concluded today at 14:30:00", res3.get_json()["message"])

        self._logout()

    def test_final_approved_schedule_takes_precedence_over_requested(self):
        """
        Verify that requested_date / requested_start_time do not determine the upload window
        when an approved schedule exists.
        """
        self._login()
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        simulated_now = datetime(2026, 10, 20, 15, 0, 0, tzinfo=tz_ist)

        # Requested was today 14:00-18:00, but approved was changed to tomorrow 14:00-18:00
        self._set_event(209, organizer_id=2, status="approved",
                        req_date="2026-10-20", req_start="14:00:00", req_end="18:00:00",
                        app_date="2026-10-21", app_start="14:00:00", app_end="18:00:00")

        with patch.object(EventModel, '_get_current_time', return_value=simulated_now):
            res = self.client.post('/api/events/209/images',
                                   data={'image': (create_test_jpeg(), 'precedence.jpg')},
                                   content_type='multipart/form-data')
            # Must be blocked because approved_date is tomorrow, even though requested_date was today!
            self.assertEqual(res.status_code, 400)
            self.assertIn("scheduled for 2026-10-21", res.get_json()["message"])

        self._logout()

    def test_unapproved_events_are_blocked(self):
        """Pending, rejected, or cancelled events cannot receive photo uploads (HTTP 400)."""
        self._login()
        today_str = date.today().isoformat()

        # 1. Pending event
        self._set_event(210, organizer_id=2, status="pending",
                        req_date=today_str, req_start="00:00:00", req_end="23:59:59",
                        app_date=None, app_start=None, app_end=None)

        res_pend = self.client.post('/api/events/210/images',
                                    data={'image': (create_test_jpeg(), 'pend.jpg')},
                                    content_type='multipart/form-data')
        self.assertEqual(res_pend.status_code, 400)
        self.assertIn("pending", res_pend.get_json()["message"].lower())

        # 2. Rejected event
        self._set_event(211, organizer_id=2, status="rejected",
                        req_date=today_str, req_start="00:00:00", req_end="23:59:59",
                        app_date=None, app_start=None, app_end=None)

        res_rej = self.client.post('/api/events/211/images',
                                   data={'image': (create_test_jpeg(), 'rej.jpg')},
                                   content_type='multipart/form-data')
        self.assertEqual(res_rej.status_code, 400)
        self.assertIn("rejected", res_rej.get_json()["message"].lower())

        # 3. Cancelled event
        self._set_event(212, organizer_id=2, status="cancelled",
                        req_date=today_str, req_start="00:00:00", req_end="23:59:59",
                        app_date=today_str, app_start="00:00:00", app_end="23:59:59")

        res_canc = self.client.post('/api/events/212/images',
                                    data={'image': (create_test_jpeg(), 'canc.jpg')},
                                    content_type='multipart/form-data')
        self.assertEqual(res_canc.status_code, 400)
        self.assertIn("cancelled", res_canc.get_json()["message"].lower())

        self._logout()

    def test_organizer_cannot_upload_to_another_organizers_event(self):
        """Organizer Alice cannot upload to Organizer Bob's event even if it is currently happening (HTTP 403)."""
        today_str = date.today().isoformat()
        # Event 213 is Bob's (organizer_id=3) and happening right now
        self._set_event(213, organizer_id=3, status="approved",
                        app_date=today_str, app_start="00:00:00", app_end="23:59:59")

        # Alice logs in
        self._login("alice@test.edu")
        res = self.client.post('/api/events/213/images',
                               data={'image': (create_test_jpeg(), 'bob_event.jpg')},
                               content_type='multipart/form-data')
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.get_json()["message"])
        self._logout()

    def test_readonly_image_review_available_after_event_concludes(self):
        """
        After the event ends, photo upload is blocked, but GET /api/events/<id>/images
        and CSRNet analysis records remain fully accessible for review.
        """
        self._login("alice@test.edu")
        today_str = date.today().isoformat()

        # 1. Create happening event and upload an image
        self._set_event(214, organizer_id=2, status="approved",
                        app_date=today_str, app_start="00:00:00", app_end="23:59:59")

        upload_res = self.client.post('/api/events/214/images',
                                      data={'image': (create_test_jpeg(), 'live_crowd.jpg')},
                                      content_type='multipart/form-data')
        self.assertEqual(upload_res.status_code, 201)
        image_id = upload_res.get_json()["image"]["id"]

        # Insert crowd analysis result
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO crowd_analyses (image_id, predicted_count, processing_status, model_name)
                    VALUES (%s, 342, 'completed', 'CSRNet');
                """, (image_id,))
        finally:
            conn.close()

        # 2. Conclude the event (move approved_date to yesterday)
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE events
                    SET approved_date = '2026-10-10', approved_start_time = '09:00:00', approved_end_time = '17:00:00'
                    WHERE id = 214;
                """)
        finally:
            conn.close()

        # 3. New upload MUST be blocked
        blocked_res = self.client.post('/api/events/214/images',
                                       data={'image': (create_test_jpeg(), 'after_concluded.jpg')},
                                       content_type='multipart/form-data')
        self.assertEqual(blocked_res.status_code, 400)
        self.assertIn("concluded on 2026-10-10", blocked_res.get_json()["message"])

        # 4. Read-only image listing and analysis MUST succeed with HTTP 200
        get_res = self.client.get('/api/events/214/images')
        self.assertEqual(get_res.status_code, 200)
        images = get_res.get_json().get("images", [])
        self.assertGreaterEqual(len(images), 1)
        self.assertEqual(images[0]["id"], image_id)
        self.assertEqual(images[0].get("predicted_count"), 342)

        self._logout()

    def test_missing_or_invalid_schedules_denied_safely(self):
        """Missing or malformed schedules are safely rejected by upload endpoint (HTTP 400)."""
        self._login()
        today_str = date.today().isoformat()

        # 1. Missing approved_date
        self._set_event(215, organizer_id=2, status="approved",
                        app_date=None, app_start="09:00:00", app_end="17:00:00")
        res1 = self.client.post('/api/events/215/images',
                                data={'image': (create_test_jpeg(), 'no_date.jpg')},
                                content_type='multipart/form-data')
        self.assertEqual(res1.status_code, 400)
        self.assertIn("confirmed management-approved schedule", res1.get_json()["message"])

        # 2. Missing approved_start_time
        self._set_event(216, organizer_id=2, status="approved",
                        app_date=today_str, app_start=None, app_end="17:00:00")
        res2 = self.client.post('/api/events/216/images',
                                data={'image': (create_test_jpeg(), 'no_start.jpg')},
                                content_type='multipart/form-data')
        self.assertEqual(res2.status_code, 400)
        self.assertIn("confirmed management-approved schedule", res2.get_json()["message"])

        # 3. Missing approved_end_time
        self._set_event(217, organizer_id=2, status="approved",
                        app_date=today_str, app_start="09:00:00", app_end=None)
        res3 = self.client.post('/api/events/217/images',
                                data={'image': (create_test_jpeg(), 'no_end.jpg')},
                                content_type='multipart/form-data')
        self.assertEqual(res3.status_code, 400)
        self.assertIn("confirmed management-approved schedule", res3.get_json()["message"])

        # 4. Start time >= end time
        self._set_event(218, organizer_id=2, status="approved",
                        app_date=today_str, app_start="18:00:00", app_end="14:00:00")
        res4 = self.client.post('/api/events/218/images',
                                data={'image': (create_test_jpeg(), 'inverted.jpg')},
                                content_type='multipart/form-data')
        self.assertEqual(res4.status_code, 400)
        self.assertIn("must precede end time", res4.get_json()["message"])

        self._logout()


if __name__ == '__main__':
    unittest.main()
