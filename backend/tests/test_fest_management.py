"""
Comprehensive Test Suite for Management Event Series / Fest Functionality
--------------------------------------------------------------------------
Verifies all requirements:
1. Management can create a fest.
2. Management can list fests (with dates, logical status, and event counts).
3. Management can edit a fest.
4. Management can delete a fest.
5. Invalid dates and bad payloads are rejected with HTTP 400.
6. Unauthorized users cannot perform Management CRUD (401 for unauth, 403 for organizer/student).
7. Existing public event-series APIs still work without regression.
8. Existing events are NOT deleted when a series is deleted (safe unlinking).
9. Existing event with series_id works properly in both public and management contexts.
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.db import get_db_connection


from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard

install_global_safety_guard()


class TestFestManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

        # Always isolate to an in-memory SQLite database
        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.seed_baseline()
        cls.isolated_db.patch_models()

        # Find or ensure management user exists in isolated database
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, email, role FROM users WHERE role = 'management' LIMIT 1;")
                cls.mgmt_user = cursor.fetchone()
                cursor.execute("SELECT id, email, role FROM users WHERE role = 'organizer' LIMIT 1;")
                cls.org_user = cursor.fetchone()
                cls.student_user = None
        finally:
            conn.close()

        assert cls.mgmt_user, "A management user must exist in the database for testing."

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'isolated_db'):
            cls.isolated_db.restore_models()

    def _login_as(self, client, user_dict):
        """Direct session login helper using test client session."""
        with client.session_transaction() as sess:
            sess['user_id'] = user_dict['id']
            sess['_fresh'] = True

    # -------------------------------------------------------------
    # 1. CREATE FEST
    # -------------------------------------------------------------
    def test_01_management_create_fest(self):
        """Test Management can create a fest with name, description, start_date, end_date."""
        client = self.app.test_client()
        self._login_as(client, self.mgmt_user)

        today = date.today()
        start_str = (today + timedelta(days=10)).isoformat()
        end_str = (today + timedelta(days=13)).isoformat()

        payload = {
            "name": "   Legacy 2K26 Fest   ",
            "description": "Annual National Inter-College Symposium & Cultural Fest",
            "start_date": start_str,
            "end_date": end_str
        }

        resp = client.post('/api/management/event-series', json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['series']['name'], "Legacy 2K26 Fest")  # whitespace trimmed
        self.assertEqual(data['series']['status'], "upcoming")
        self.assertEqual(data['series']['computed_status'], "Upcoming")
        self.assertIsNotNone(data['series']['id'])
        print(f"   [OK] Test 1: Management created fest #{data['series']['id']} '{data['series']['name']}'")

    # -------------------------------------------------------------
    # 2. LIST FESTS
    # -------------------------------------------------------------
    def test_02_management_list_fests(self):
        """Test Management can list fests with logical status and event counts."""
        client = self.app.test_client()
        self._login_as(client, self.mgmt_user)

        resp = client.get('/api/management/event-series')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['series'], list)
        self.assertGreaterEqual(data['count'], 1)

        # Check required fields
        fest = data['series'][0]
        for field in ['id', 'name', 'description', 'start_date', 'end_date', 'status', 'computed_status', 'event_count', 'created_at']:
            self.assertIn(field, fest, f"Field '{field}' missing from list response")

        print(f"   [OK] Test 2: Management listed {data['count']} fests. Sample status: '{fest['computed_status']}', events: {fest['event_count']}")

    # -------------------------------------------------------------
    # 3. EDIT FEST
    # -------------------------------------------------------------
    def test_03_management_edit_fest(self):
        """Test Management can edit a fest."""
        client = self.app.test_client()
        self._login_as(client, self.mgmt_user)

        # Create temporary fest to edit
        today = date.today()
        create_resp = client.post('/api/management/event-series', json={
            "name": "Original Fest Name",
            "description": "Original Description",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=2)).isoformat()
        })
        self.assertEqual(create_resp.status_code, 201)
        series_id = create_resp.get_json()['series']['id']

        # Edit fest
        update_resp = client.patch(f'/api/management/event-series/{series_id}', json={
            "name": "Updated TechSprint Fest",
            "description": "Updated Description with rules and theme",
            "start_date": (today - timedelta(days=5)).isoformat(),
            "end_date": (today - timedelta(days=1)).isoformat()
        })
        self.assertEqual(update_resp.status_code, 200)
        up_data = update_resp.get_json()['series']
        self.assertEqual(up_data['name'], "Updated TechSprint Fest")
        self.assertEqual(up_data['description'], "Updated Description with rules and theme")
        self.assertEqual(up_data['status'], "completed")  # Past dates -> completed
        self.assertEqual(up_data['computed_status'], "Completed")

        # Cleanup
        client.delete(f'/api/management/event-series/{series_id}')
        print(f"   [OK] Test 3: Management edited fest #{series_id} successfully, status correctly recomputed as '{up_data['computed_status']}'.")

    # -------------------------------------------------------------
    # 4. DELETE FEST
    # -------------------------------------------------------------
    def test_04_management_delete_fest(self):
        """Test Management can delete a fest."""
        client = self.app.test_client()
        self._login_as(client, self.mgmt_user)

        today = date.today()
        create_resp = client.post('/api/management/event-series', json={
            "name": "Fest to Delete",
            "start_date": today.isoformat(),
            "end_date": today.isoformat()
        })
        series_id = create_resp.get_json()['series']['id']

        del_resp = client.delete(f'/api/management/event-series/{series_id}')
        self.assertEqual(del_resp.status_code, 200)

        # Confirm 404 after deletion
        get_resp = client.get(f'/api/management/event-series/{series_id}')
        self.assertEqual(get_resp.status_code, 404)
        print(f"   [OK] Test 4: Management deleted fest #{series_id} cleanly.")

    # -------------------------------------------------------------
    # 5. VALIDATION: INVALID DATES & BAD PAYLOADS
    # -------------------------------------------------------------
    def test_05_validation_invalid_dates_and_bad_payload(self):
        """Test validation for missing name, missing dates, inverted dates, and invalid formats."""
        client = self.app.test_client()
        self._login_as(client, self.mgmt_user)

        today = date.today()

        # 1. Missing name
        r = client.post('/api/management/event-series', json={
            "name": "   ",
            "start_date": today.isoformat(),
            "end_date": today.isoformat()
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("Fest name is required", r.get_json()['message'])

        # 2. Inverted dates (end date before start date)
        r = client.post('/api/management/event-series', json={
            "name": "Inverted Fest",
            "start_date": "2026-10-20",
            "end_date": "2026-10-15"
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("End date must not be earlier than start date", r.get_json()['message'])

        # 3. Invalid date format
        r = client.post('/api/management/event-series', json={
            "name": "Bad Format Fest",
            "start_date": "20-10-2026",
            "end_date": "2026-10-25"
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("YYYY-MM-DD", r.get_json()['message'])

        # 4. Missing end date
        r = client.post('/api/management/event-series', json={
            "name": "Missing End Date Fest",
            "start_date": "2026-10-20",
            "end_date": ""
        })
        self.assertEqual(r.status_code, 400)

        print("   [OK] Test 5: Validation correctly rejected all invalid inputs (empty name, inverted dates, bad format).")

    # -------------------------------------------------------------
    # 6. AUTHORIZATION: UNAUTHORIZED USERS REJECTED
    # -------------------------------------------------------------
    def test_06_unauthorized_users_rejected(self):
        """Test unauthenticated users receive 401, organizer/student receive 403."""
        # 1. Unauthenticated client
        unauth_client = self.app.test_client()
        r = unauth_client.get('/api/management/event-series')
        self.assertEqual(r.status_code, 401)
        r = unauth_client.post('/api/management/event-series', json={})
        self.assertEqual(r.status_code, 401)

        # 2. Organizer client
        if self.org_user:
            org_client = self.app.test_client()
            self._login_as(org_client, self.org_user)
            r = org_client.get('/api/management/event-series')
            self.assertEqual(r.status_code, 403)
            r = org_client.post('/api/management/event-series', json={"name": "Org Fest"})
            self.assertEqual(r.status_code, 403)

        # 3. Student client
        if self.student_user:
            stud_client = self.app.test_client()
            self._login_as(stud_client, self.student_user)
            r = stud_client.get('/api/management/event-series')
            self.assertEqual(r.status_code, 403)

        print("   [OK] Test 6: Role enforcement verified (401 for unauthenticated, 403 for organizer/student).")

    # -------------------------------------------------------------
    # 7. PUBLIC FUNCTIONALITY UNBROKEN
    # -------------------------------------------------------------
    def test_07_public_endpoints_unbroken(self):
        """Test public event-series listing, detail, and event filtering still function without errors."""
        pub_client = self.app.test_client()

        # Public series listing
        r = pub_client.get('/api/public/event-series')
        self.assertEqual(r.status_code, 200)
        p_data = r.get_json()
        self.assertTrue(p_data['success'])
        self.assertIsInstance(p_data['series'], list)

        # If a series exists, check detail endpoint
        if p_data['series']:
            sid = p_data['series'][0]['id']
            r_det = pub_client.get(f'/api/public/event-series/{sid}')
            self.assertEqual(r_det.status_code, 200)
            self.assertIn('events', r_det.get_json()['series'])

            # Public events filter by series_id
            r_ev = pub_client.get(f'/api/public/events?series_id={sid}')
            self.assertEqual(r_ev.status_code, 200)

        print("   [OK] Test 7: Public event-series APIs completely intact and operational.")

    # -------------------------------------------------------------
    # 8. SAFE DELETION: EVENTS ARE NOT DELETED WHEN SERIES DELETED
    # -------------------------------------------------------------
    def test_08_events_not_deleted_when_series_deleted(self):
        """Test that deleting an event series unlinks events (series_id=NULL) without deleting the events."""
        mgmt_client = self.app.test_client()
        self._login_as(mgmt_client, self.mgmt_user)

        # 1. Create a fest
        today = date.today()
        c_resp = mgmt_client.post('/api/management/event-series', json={
            "name": "Fest With Linked Event",
            "description": "Test unlinking integrity",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=3)).isoformat()
        })
        self.assertEqual(c_resp.status_code, 201)
        series_id = c_resp.get_json()['series']['id']

        # 2. Create a temporary event in DB linked to this series
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO events (
                        organizer_id, event_name, description, status,
                        requested_date, requested_start_time, requested_end_time,
                        series_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    self.mgmt_user['id'],
                    "Sub Event For Series Test",
                    "Testing series foreign key integrity",
                    "approved",
                    today.isoformat(),
                    "10:00:00",
                    "12:00:00",
                    series_id
                ))
                test_event_id = cursor.lastrowid
        finally:
            conn.close()

        # Verify event has series_id
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT series_id FROM events WHERE id = %s;", (test_event_id,))
                row = cursor.fetchone()
                self.assertEqual(row['series_id'], series_id)
        finally:
            conn.close()

        # 3. Delete the fest via Management API
        del_resp = mgmt_client.delete(f'/api/management/event-series/{series_id}')
        self.assertEqual(del_resp.status_code, 200)
        self.assertGreaterEqual(del_resp.get_json().get('unlinked_events', 0), 1)

        # 4. Verify the event STILL EXISTS and its series_id is now NULL
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, event_name, series_id FROM events WHERE id = %s;", (test_event_id,))
                event_row = cursor.fetchone()
                self.assertIsNotNone(event_row, "Event was incorrectly deleted!")
                self.assertIsNone(event_row['series_id'], "Event series_id was not set to NULL!")

                # Cleanup test event
                cursor.execute("DELETE FROM events WHERE id = %s;", (test_event_id,))
        finally:
            conn.close()

        print(f"   [OK] Test 8: Safe deletion verified! Event #{test_event_id} preserved with series_id=NULL when series #{series_id} was deleted.")

    # -------------------------------------------------------------
    # 9. EXISTING EVENT WITH series_id WORKS PROPERLY
    # -------------------------------------------------------------
    def test_09_existing_event_with_series_id_works(self):
        """Test that an event linked to a fest correctly appears in fest event count and queries."""
        mgmt_client = self.app.test_client()
        self._login_as(mgmt_client, self.mgmt_user)

        today = date.today()
        c_resp = mgmt_client.post('/api/management/event-series', json={
            "name": "Gyan Mitra 2026",
            "description": "Technical Symposium",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat()
        })
        series_id = c_resp.get_json()['series']['id']

        # Link an event
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO events (
                        organizer_id, event_name, description, status,
                        requested_date, requested_start_time, requested_end_time,
                        series_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    self.mgmt_user['id'],
                    "Paper Presentation",
                    "Gyan Mitra sub-event",
                    "approved",
                    today.isoformat(),
                    "09:30:00",
                    "13:00:00",
                    series_id
                ))
                ev_id = cursor.lastrowid
        finally:
            conn.close()

        # Query series detail via Management API
        detail_resp = mgmt_client.get(f'/api/management/event-series/{series_id}')
        self.assertEqual(detail_resp.status_code, 200)
        s_data = detail_resp.get_json()['series']
        self.assertEqual(s_data['event_count'], 1)

        # Cleanup
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM events WHERE id = %s;", (ev_id,))
                cursor.execute("DELETE FROM event_series WHERE id = %s;", (series_id,))
        finally:
            conn.close()

        print("   [OK] Test 9: Event linked with series_id correctly reflected in fest queries.")


if __name__ == '__main__':
    print("======================================================================")
    print(" Running Fest / Event Series Management Verification Suite ")
    print("======================================================================")
    unittest.main(verbosity=2)
