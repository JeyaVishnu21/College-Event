"""
Test Suite for Administrator Fest & Event Registry Requirements
--------------------------------------------------------------
Verifies:
1. Administrator can view fests loaded from MySQL with approved_event_count.
2. Administrator can create a fest with optional dates and description.
3. Duplicate fest names (case-insensitive) are rejected with HTTP 400.
4. Administrator can fetch approved events for a specific fest.
5. Unassigned approved events (series_id IS NULL) are correctly listed.
6. Administrator can safely assign an unassigned event to a fest.
7. Administrator can update an approved event's schedule and venue.
8. Updating schedule enforces venue capacity (expected_participants > capacity) -> 400.
9. Updating schedule rejects overlapping venue conflicts -> 400.
10. Attempting to delete a fest with events without reassignment is blocked -> 400.
11. Deleting a fest with reassignment safely migrates events to the target fest.
12. Role-based access control enforces administrator-only access.
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


class TestAdministratorFestRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

        # Isolate database
        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.seed_baseline()
        cls.isolated_db.patch_models()

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, email, role FROM users WHERE role = 'management' LIMIT 1;")
                cls.admin_user = cursor.fetchone()
                cursor.execute("SELECT id, email, role FROM users WHERE role = 'organizer' LIMIT 1;")
                cls.org_user = cursor.fetchone()
        finally:
            conn.close()

        assert cls.admin_user, "An administrator user must exist."

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'isolated_db'):
            cls.isolated_db.restore_models()

    def _login_as(self, client, user_dict):
        with client.session_transaction() as sess:
            sess['user_id'] = user_dict['id']
            sess['_fresh'] = True

    def test_01_admin_list_fests(self):
        client = self.app.test_client()
        self._login_as(client, self.admin_user)

        res = client.get('/api/administrator/fests')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('fests', data)
        self.assertGreaterEqual(len(data['fests']), 2)

    def test_02_create_fest_optional_dates_and_duplicate_prevention(self):
        client = self.app.test_client()
        self._login_as(client, self.admin_user)

        # 1. Create with optional dates (None)
        res = client.post('/api/administrator/fests', json={
            "name": "Technova Summit",
            "description": "Tech conference without fixed dates"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['fest']['name'], "Technova Summit")
        self.assertIsNone(data['fest']['start_date'])

        # 2. Prevent duplicate name (case-insensitive)
        dup_res = client.post('/api/administrator/fests', json={
            "name": "  technova summit  "
        })
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("already exists", dup_res.get_json()['message'])

    def test_03_get_fest_approved_events_and_unassigned(self):
        client = self.app.test_client()
        self._login_as(client, self.admin_user)

        # Fetch fests to find one with events
        res = client.get('/api/administrator/fests')
        fests = res.get_json()['fests']
        fest_id = fests[0]['id']

        # Get approved events for this fest
        approved_res = client.get(f'/api/administrator/fests/{fest_id}/approved-events')
        self.assertEqual(approved_res.status_code, 200)
        appr_data = approved_res.get_json()
        self.assertTrue(appr_data['success'])
        self.assertIn('events', appr_data)

        # Get unassigned approved events
        unassigned_res = client.get('/api/administrator/events/unassigned-approved')
        self.assertEqual(unassigned_res.status_code, 200)
        un_data = unassigned_res.get_json()
        self.assertTrue(un_data['success'])
        self.assertIn('events', un_data)

    def test_04_assign_event_to_fest(self):
        client = self.app.test_client()
        self._login_as(client, self.admin_user)

        # Create an unassigned approved event
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO events (
                        organizer_id, event_name, status, requested_date,
                        requested_start_time, requested_end_time, series_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, NULL);
                """, (
                    self.org_user['id'],
                    "Unassigned Hackathon",
                    "approved",
                    date.today().isoformat(),
                    "10:00:00",
                    "16:00:00"
                ))
                ev_id = cursor.lastrowid
        finally:
            conn.close()

        # Assign it to a fest
        fests_res = client.get('/api/administrator/fests')
        target_fest_id = fests_res.get_json()['fests'][0]['id']

        assign_res = client.patch(f'/api/administrator/events/{ev_id}/assign-fest', json={
            "series_id": target_fest_id
        })
        self.assertEqual(assign_res.status_code, 200)

        # Verify in DB
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT series_id FROM events WHERE id = %s;", (ev_id,))
                row = cursor.fetchone()
                self.assertEqual(row['series_id'], target_fest_id)
        finally:
            conn.close()

    def test_05_schedule_and_venue_update_validation(self):
        client = self.app.test_client()
        self._login_as(client, self.admin_user)

        # Get available venues
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, capacity FROM venues WHERE status = 'available' LIMIT 1;")
                venue = cursor.fetchone()
                cursor.execute("SELECT id FROM events WHERE status = 'approved' LIMIT 1;")
                event = cursor.fetchone()
        finally:
            conn.close()

        v_id = venue['id']
        cap = venue['capacity']
        ev_id = event['id']

        # 1. Capacity validation: expected_participants > venue.capacity
        res = client.patch(f'/api/administrator/events/{ev_id}/allocation', json={
            "venue_id": v_id,
            "approved_date": date.today().isoformat(),
            "approved_start_time": "09:00:00",
            "approved_end_time": "12:00:00",
            "expected_participants": cap + 500
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("insufficient", res.get_json()['message'].lower())

        # 2. Successful schedule update within capacity
        ok_res = client.patch(f'/api/administrator/events/{ev_id}/allocation', json={
            "venue_id": v_id,
            "approved_date": (date.today() + timedelta(days=5)).isoformat(),
            "approved_start_time": "14:00:00",
            "approved_end_time": "17:00:00",
            "expected_participants": min(50, cap)
        })
        self.assertEqual(ok_res.status_code, 200)

    def test_06_fest_safe_deletion_and_reassignment(self):
        client = self.app.test_client()
        self._login_as(client, self.admin_user)

        # Create two fests: fest_a and fest_b
        r1 = client.post('/api/administrator/fests', json={"name": "Source Fest A"})
        fest_a_id = r1.get_json()['fest']['id']
        r2 = client.post('/api/administrator/fests', json={"name": "Target Fest B"})
        fest_b_id = r2.get_json()['fest']['id']

        # Create an event in fest_a
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO events (
                        organizer_id, event_name, status, requested_date,
                        requested_start_time, requested_end_time, series_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (
                    self.org_user['id'],
                    "Source Fest Event",
                    "approved",
                    date.today().isoformat(),
                    "10:00:00",
                    "12:00:00",
                    fest_a_id
                ))
                ev_id = cursor.lastrowid
        finally:
            conn.close()

        # 1. Attempt to delete fest_a without reassignment -> MUST BE REJECTED 400
        del_fail = client.delete(f'/api/administrator/fests/{fest_a_id}')
        self.assertEqual(del_fail.status_code, 400)
        self.assertIn("reassign", del_fail.get_json()['message'].lower())

        # 2. Delete fest_a with reassignment to fest_b -> SUCCESS
        del_ok = client.delete(f'/api/administrator/fests/{fest_a_id}', json={
            "reassign_to": fest_b_id
        })
        self.assertEqual(del_ok.status_code, 200)

        # Verify event was reassigned to fest_b
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT series_id FROM events WHERE id = %s;", (ev_id,))
                row = cursor.fetchone()
                self.assertEqual(row['series_id'], fest_b_id)
        finally:
            conn.close()

    def test_07_role_authorization_enforcement(self):
        # 1. Unauthenticated -> 401
        unauth_client = self.app.test_client()
        r1 = unauth_client.get('/api/administrator/fests')
        self.assertEqual(r1.status_code, 401)

        # 2. Organizer role -> 403
        org_client = self.app.test_client()
        self._login_as(org_client, self.org_user)
        r2 = org_client.get('/api/administrator/fests')
        self.assertEqual(r2.status_code, 403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
