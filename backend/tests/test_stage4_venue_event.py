"""
Stage 4 Venue & Event Management Verification Suite
---------------------------------------------------
Verifies all 20 Acceptance Tests:
  TEST 1:  Management can create a venue.
  TEST 2:  Management can view venues.
  TEST 3:  Management can update venue information/status.
  TEST 4:  Management can delete a safe venue.
  TEST 5:  Organizer cannot create/update/delete venues (HTTP 403).
  TEST 6:  Organizer can create an event request.
  TEST 7:  Event is automatically associated with the authenticated organizer.
  TEST 8:  Organizer can view their own events.
  TEST 9:  Organizer cannot view another organizer's event (HTTP 403).
  TEST 10: Management can view pending event requests.
  TEST 11: Management can approve an event.
  TEST 12: Management can reject an event (with optional rejection reason).
  TEST 13: Management can allocate a venue/date/time.
  TEST 14: Management cannot allocate an unavailable venue (HTTP 400).
  TEST 15: System prevents conflicting venue/time allocations (HTTP 409).
  TEST 16: Management can modify an existing final allocation.
  TEST 17: Organizer can see the updated final allocation.
  TEST 18: Unauthenticated users cannot access protected event/venue APIs (HTTP 401).
  TEST 19: Organizer cannot access management-only APIs (HTTP 403).
  TEST 20: Invalid event/venue input is rejected correctly (HTTP 400).
"""

import sys
import unittest
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.settings import settings
from config.db import check_db_status
import config.db
from middleware.auth import hash_password


class SQLitePyMySQLCursorAdapter:
    """Adapts an in-memory SQLite cursor to mimic PyMySQL DictCursor with %s support."""
    def __init__(self, sqlite_conn):
        self._conn = sqlite_conn
        self._cur = sqlite_conn.cursor()

    def execute(self, query, params=None):
        sqlite_query = query.replace('%s', '?')
        if params is not None:
            res = self._cur.execute(sqlite_query, params)
        else:
            res = self._cur.execute(sqlite_query)
        self._conn.commit()
        return res

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SQLitePyMySQLConnectionAdapter:
    """Adapts an in-memory SQLite connection to mimic PyMySQL connection."""
    def __init__(self, sqlite_conn):
        self._conn = sqlite_conn

    def cursor(self):
        return SQLitePyMySQLCursorAdapter(self._conn)

    def close(self):
        pass


class TestStage4VenueEventManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Configure test environment and seed test users and venues."""
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'stage4-test-secret-key-2026'

        # Always isolate to an in-memory SQLite database
        try:
            from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
        except ImportError:
            from db_guard import IsolatedTestDatabase, install_global_safety_guard
        install_global_safety_guard()

        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.seed_baseline()
        cls.isolated_db.patch_models()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "isolated_db"):
            cls.isolated_db.restore_models()

    def setUp(self):
        self.client = self.app.test_client()

    def _login_as(self, email, password):
        res = self.client.post('/api/auth/login', json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------
    # VENUE MANAGEMENT TESTS (TEST 1 - 5)
    # -------------------------------------------------------------
    def test_01_management_can_create_venue(self):
        """TEST 1: Management can create a venue."""
        self._login_as("admin@college.edu", "Admin@123")
        payload = {
            "name": "Science Lab Complex",
            "location": "Block C, Ground Floor",
            "capacity": 150,
            "status": "available"
        }
        res = self.client.post('/api/venues', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data['venue']['name'], "Science Lab Complex")
        self.assertEqual(data['venue']['capacity'], 150)
        print("   [OK] TEST 1: Management can create a venue.")

    def test_02_management_can_view_venues(self):
        """TEST 2: Management can view venues."""
        self._login_as("admin@college.edu", "Admin@123")
        res = self.client.get('/api/venues')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('venues', data)
        self.assertGreaterEqual(len(data['venues']), 2)
        print("   [OK] TEST 2: Management can view venues.")

    def test_03_management_can_update_venue(self):
        """TEST 3: Management can update venue information and status."""
        self._login_as("admin@college.edu", "Admin@123")
        # Update venue 2
        payload = {
            "name": "Renovated Seminar Hall",
            "location": "Block B, 2nd Floor (East Wing)",
            "capacity": 300,
            "status": "available"
        }
        res = self.client.put('/api/venues/2', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['venue']['name'], "Renovated Seminar Hall")
        self.assertEqual(data['venue']['capacity'], 300)

        # Toggle status to unavailable
        patch_res = self.client.patch('/api/venues/2/status', json={"status": "unavailable"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()['venue']['status'], "unavailable")

        # Toggle back to available for subsequent tests
        self.client.patch('/api/venues/2/status', json={"status": "available"})
        print("   [OK] TEST 3: Management can update venue information/status.")

    def test_04_management_can_delete_safe_venue(self):
        """TEST 4: Management can delete a safe venue (one without associated events)."""
        self._login_as("admin@college.edu", "Admin@123")
        # Create a temporary venue to delete safely
        create_res = self.client.post('/api/venues', json={
            "name": "Temporary Tent Pavilion",
            "location": "North Lawn",
            "capacity": 80,
            "status": "available"
        })
        temp_id = create_res.get_json()['venue']['id']

        # Delete the temporary venue
        del_res = self.client.delete(f'/api/venues/{temp_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertIn("deleted successfully", del_res.get_json()['message'])

        # Verify it no longer exists
        get_res = self.client.get(f'/api/venues/{temp_id}')
        self.assertEqual(get_res.status_code, 404)
        print("   [OK] TEST 4: Management can delete a safe venue.")

    def test_05_organizer_cannot_modify_venues(self):
        """TEST 5: Organizer cannot create, update, or delete venues (HTTP 403)."""
        self._login_as("john.organizer@college.edu", "Organizer@123")

        # Attempt to create venue
        post_res = self.client.post('/api/venues', json={"name": "Hacked Hall", "location": "Roof"})
        self.assertEqual(post_res.status_code, 403)

        # Attempt to update venue 1
        put_res = self.client.put('/api/venues/1', json={"name": "Hacked Name", "location": "Roof", "capacity": 10})
        self.assertEqual(put_res.status_code, 403)

        # Attempt to delete venue 1
        del_res = self.client.delete('/api/venues/1')
        self.assertEqual(del_res.status_code, 403)
        print("   [OK] TEST 5: Organizer cannot create/update/delete venues (403).")

    # -------------------------------------------------------------
    # ORGANIZER EVENT TESTS (TEST 6 - 9)
    # -------------------------------------------------------------
    def test_06_and_07_organizer_can_create_event_request(self):
        """TEST 6 & 7: Organizer can create an event request automatically bound to session['user_id']."""
        self._login_as("john.organizer@college.edu", "Organizer@123")
        payload = {
            "series_id": 1,
            "event_name": "Robotics Championship 2026",
            "description": "Annual campus robot combat and maze solving contest.",
            "requested_date": "2026-10-15",
            "requested_start_time": "09:00:00",
            "requested_end_time": "17:00:00",
            "venue_id": 1,
            "organizer_id": 999  # Attempt to spoof organizer ID — should be ignored!
        }
        res = self.client.post('/api/events', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        event = data['event']

        self.assertEqual(event['event_name'], "Robotics Championship 2026")
        self.assertEqual(event['status'], "pending")
        # TEST 7: Bound strictly to John's user ID (2), not spoofed 999!
        self.assertEqual(event['organizer_id'], 2)
        print("   [OK] TEST 6 & 7: Organizer created event request securely bound to session['user_id'].")

    def test_08_organizer_can_view_own_events(self):
        """TEST 8: Organizer can view their own events list."""
        self._login_as("john.organizer@college.edu", "Organizer@123")
        res = self.client.get('/api/events')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('events', data)
        # All events returned must belong to John (id 2)
        for ev in data['events']:
            self.assertEqual(ev['organizer_id'], 2)
        print("   [OK] TEST 8: Organizer can view their own events.")

    def test_09_organizer_cannot_view_another_organizers_event(self):
        """TEST 9: Organizer cannot view another organizer's event details (HTTP 403)."""
        # 1. Sarah (Organizer 2) creates an event
        self._login_as("sarah.organizer@college.edu", "Organizer2@123")
        create_res = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Sarah Private Art Expo",
            "description": "Art gallery display.",
            "requested_date": "2026-10-20",
            "requested_start_time": "10:00:00",
            "requested_end_time": "14:00:00",
            "venue_id": 2
        })
        sarah_event_id = create_res.get_json()['event']['id']

        # 2. John (Organizer 1) attempts to view Sarah's event details
        self._login_as("john.organizer@college.edu", "Organizer@123")
        inspect_res = self.client.get(f'/api/events/{sarah_event_id}')
        self.assertEqual(inspect_res.status_code, 403)
        self.assertIn("Access denied", inspect_res.get_json()['message'])
        print("   [OK] TEST 9: Organizer cannot view another organizer's event (403).")

    # -------------------------------------------------------------
    # MANAGEMENT REVIEW & APPROVAL/REJECTION (TEST 10 - 12)
    # -------------------------------------------------------------
    def test_10_management_can_view_pending_requests(self):
        """TEST 10: Management can view pending event requests."""
        self._login_as("admin@college.edu", "Admin@123")
        res = self.client.get('/api/management/events/pending')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('events', data)
        for ev in data['events']:
            self.assertEqual(ev['status'], "pending")
        print("   [OK] TEST 10: Management can view pending event requests.")

    def test_11_management_can_approve_event(self):
        """TEST 11: Management can approve an event."""
        # 1. Organizer submits an event
        self._login_as("john.organizer@college.edu", "Organizer@123")
        create_res = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Hackathon 2026",
            "description": "24 hour hackathon.",
            "requested_date": "2026-11-01",
            "requested_start_time": "10:00:00",
            "requested_end_time": "18:00:00",
            "venue_id": 1
        })
        event_id = create_res.get_json()['event']['id']

        # 2. Management approves it
        self._login_as("admin@college.edu", "Admin@123")
        patch_res = self.client.patch(f'/api/management/events/{event_id}/status', json={"status": "approved"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()['event']['status'], "approved")
        print("   [OK] TEST 11: Management can approve an event.")

    def test_12_management_can_reject_event_with_reason(self):
        """TEST 12: Management can reject an event with an optional rejection reason."""
        # 1. Organizer submits an event
        self._login_as("john.organizer@college.edu", "Organizer@123")
        create_res = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Overnight DJ Party",
            "description": "Loud music party.",
            "requested_date": "2026-11-05",
            "requested_start_time": "20:00:00",
            "requested_end_time": "23:00:00",
            "venue_id": 1
        })
        self.assertEqual(create_res.status_code, 201)
        event_id = create_res.get_json()['event']['id']

        # 2. Management rejects it with reason
        self._login_as("admin@college.edu", "Admin@123")
        patch_res = self.client.patch(f'/api/management/events/{event_id}/status', json={
            "status": "rejected",
            "rejection_reason": "Overnight sound amplification is not permitted on weekdays."
        })
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.get_json()['event']
        self.assertEqual(data['status'], "rejected")
        self.assertEqual(data['rejection_reason'], "Overnight sound amplification is not permitted on weekdays.")
        print("   [OK] TEST 12: Management can reject an event with optional reason.")

    # -------------------------------------------------------------
    # VENUE ALLOCATION & CONFLICT CHECKING (TEST 13 - 17)
    # -------------------------------------------------------------
    def test_13_management_can_allocate_venue_and_schedule(self):
        """TEST 13: Management can allocate final venue and schedule."""
        # 1. Submit event request
        self._login_as("john.organizer@college.edu", "Organizer@123")
        create_res = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Coding Olympiad",
            "description": "Competitive programming.",
            "requested_date": "2026-11-10",
            "requested_start_time": "09:00:00",
            "requested_end_time": "12:00:00",
            "venue_id": 2
        })
        event_id = create_res.get_json()['event']['id']

        # 2. Management allocates final venue (e.g. Venue 1) and schedule (10:00 - 13:00)
        self._login_as("admin@college.edu", "Admin@123")
        alloc_res = self.client.patch(f'/api/management/events/{event_id}/allocation', json={
            "venue_id": 1,
            "approved_date": "2026-11-10",
            "approved_start_time": "10:00:00",
            "approved_end_time": "13:00:00"
        })
        self.assertEqual(alloc_res.status_code, 200)
        ev = alloc_res.get_json()['event']
        self.assertEqual(ev['status'], "approved")
        self.assertEqual(ev['venue_id'], 1)
        self.assertEqual(str(ev['approved_start_time']), "10:00:00")
        self.assertEqual(str(ev['approved_end_time']), "13:00:00")
        # Ensure requested fields remain preserved
        self.assertEqual(str(ev['requested_start_time']), "09:00:00")
        print("   [OK] TEST 13: Management can allocate venue/date/time.")

    def test_14_cannot_allocate_unavailable_venue(self):
        """TEST 14: Management cannot allocate an unavailable venue (HTTP 400)."""
        self._login_as("admin@college.edu", "Admin@123")
        # 1. Mark venue 2 as unavailable
        self.client.patch('/api/venues/2/status', json={"status": "unavailable"})

        # 2. Attempt to allocate venue 2 to an event
        # First create event
        self._login_as("john.organizer@college.edu", "Organizer@123")
        c_res = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Test Unavailable Venue",
            "requested_date": "2026-11-12",
            "requested_start_time": "10:00:00",
            "requested_end_time": "12:00:00"
        })
        event_id = c_res.get_json()['event']['id']

        # Attempt allocation
        self._login_as("admin@college.edu", "Admin@123")
        alloc_res = self.client.patch(f'/api/management/events/{event_id}/allocation', json={
            "venue_id": 2,
            "approved_date": "2026-11-12",
            "approved_start_time": "10:00:00",
            "approved_end_time": "12:00:00"
        })
        self.assertEqual(alloc_res.status_code, 400)
        self.assertIn("unavailable", alloc_res.get_json()['message'])

        # Reset venue 2 to available
        self.client.patch('/api/venues/2/status', json={"status": "available"})
        print("   [OK] TEST 14: Management cannot allocate an unavailable venue (400).")

    def test_15_prevents_conflicting_venue_time_allocations(self):
        """TEST 15: System strictly prevents conflicting venue/time allocations (HTTP 409)."""
        self._login_as("admin@college.edu", "Admin@123")

        # Event A: Main Auditorium on 2026-11-20 from 10:00 to 14:00
        self._login_as("john.organizer@college.edu", "Organizer@123")
        ev_a = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Event Alpha",
            "requested_date": "2026-11-20",
            "requested_start_time": "10:00:00",
            "requested_end_time": "14:00:00"
        }).get_json()['event']['id']

        self._login_as("admin@college.edu", "Admin@123")
        self.client.patch(f'/api/management/events/{ev_a}/allocation', json={
            "venue_id": 1,
            "approved_date": "2026-11-20",
            "approved_start_time": "10:00:00",
            "approved_end_time": "14:00:00"
        })

        # Event B: Attempt to allocate Main Auditorium on same day with overlapping time 12:00 to 16:00
        self._login_as("sarah.organizer@college.edu", "Organizer2@123")
        ev_b = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Event Beta Overlap",
            "requested_date": "2026-11-20",
            "requested_start_time": "12:00:00",
            "requested_end_time": "16:00:00"
        }).get_json()['event']['id']

        self._login_as("admin@college.edu", "Admin@123")
        conflict_res = self.client.patch(f'/api/management/events/{ev_b}/allocation', json={
            "venue_id": 1,
            "approved_date": "2026-11-20",
            "approved_start_time": "12:00:00",
            "approved_end_time": "16:00:00"
        })
        self.assertEqual(conflict_res.status_code, 409)
        self.assertIn("conflict", conflict_res.get_json()['message'].lower())
        print("   [OK] TEST 15: System prevents conflicting venue/time allocations (409).")

    def test_16_and_17_modify_existing_allocation_and_organizer_views_it(self):
        """TEST 16 & 17: Management modifies existing allocation and organizer sees updated schedule."""
        # 1. Organizer submits event
        self._login_as("john.organizer@college.edu", "Organizer@123")
        ev_id = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Debate Championship",
            "requested_date": "2026-11-25",
            "requested_start_time": "10:00:00",
            "requested_end_time": "12:00:00",
            "venue_id": 1
        }).get_json()['event']['id']

        # 2. Initial allocation: Venue 1, 10:00 - 12:00
        self._login_as("admin@college.edu", "Admin@123")
        self.client.patch(f'/api/management/events/{ev_id}/allocation', json={
            "venue_id": 1,
            "approved_date": "2026-11-25",
            "approved_start_time": "10:00:00",
            "approved_end_time": "12:00:00"
        })

        # 3. Modification (TEST 16): Change venue to Venue 2 and time to 14:00 - 16:00
        mod_res = self.client.patch(f'/api/management/events/{ev_id}/allocation', json={
            "venue_id": 2,
            "approved_date": "2026-11-25",
            "approved_start_time": "14:00:00",
            "approved_end_time": "16:00:00"
        })
        self.assertEqual(mod_res.status_code, 200)
        self.assertEqual(mod_res.get_json()['event']['venue_id'], 2)
        print("   [OK] TEST 16: Management can modify an existing final allocation.")

        # 4. Organizer view check (TEST 17)
        self._login_as("john.organizer@college.edu", "Organizer@123")
        org_view = self.client.get(f'/api/events/{ev_id}')
        self.assertEqual(org_view.status_code, 200)
        ev_data = org_view.get_json()['event']
        self.assertEqual(ev_data['venue_id'], 2)
        self.assertEqual(str(ev_data['approved_start_time']), "14:00:00")
        self.assertEqual(str(ev_data['approved_end_time']), "16:00:00")
        # Organizer's original requested times are still intact!
        self.assertEqual(str(ev_data['requested_start_time']), "10:00:00")
        print("   [OK] TEST 17: Organizer can see updated final allocation with requested values preserved.")

    # -------------------------------------------------------------
    # SECURITY & VALIDATION TESTS (TEST 18 - 20)
    # -------------------------------------------------------------
    def test_18_unauthenticated_users_cannot_access_apis(self):
        """TEST 18: Unauthenticated users cannot access protected event or venue APIs (HTTP 401)."""
        # Venue routes
        self.assertEqual(self.client.get('/api/venues').status_code, 401)
        self.assertEqual(self.client.post('/api/venues', json={}).status_code, 401)
        # Event routes
        self.assertEqual(self.client.get('/api/events').status_code, 401)
        self.assertEqual(self.client.post('/api/events', json={}).status_code, 401)
        self.assertEqual(self.client.get('/api/management/events').status_code, 401)
        print("   [OK] TEST 18: Unauthenticated users cannot access protected APIs (401).")

    def test_19_organizer_cannot_access_management_apis(self):
        """TEST 19: Organizer cannot access management-only APIs (HTTP 403)."""
        self._login_as("john.organizer@college.edu", "Organizer@123")
        self.assertEqual(self.client.get('/api/management/events').status_code, 403)
        self.assertEqual(self.client.get('/api/management/events/pending').status_code, 403)
        self.assertEqual(self.client.patch('/api/management/events/1/status', json={}).status_code, 403)
        self.assertEqual(self.client.patch('/api/management/events/1/allocation', json={}).status_code, 403)
        print("   [OK] TEST 19: Organizer cannot access management-only APIs (403).")

    def test_20_invalid_event_and_venue_input_rejected(self):
        """TEST 20: Invalid event and venue inputs are rejected correctly (HTTP 400)."""
        self._login_as("admin@college.edu", "Admin@123")
        # 1. Invalid venue capacity (negative)
        neg_cap = self.client.post('/api/venues', json={"name": "Bad Venue", "location": "Ground", "capacity": -10})
        self.assertEqual(neg_cap.status_code, 400)

        # 2. Invalid venue status
        bad_status = self.client.post('/api/venues', json={"name": "Bad Status", "location": "Ground", "status": "unknown"})
        self.assertEqual(bad_status.status_code, 400)

        # 3. Invalid event times (start after end)
        self._login_as("john.organizer@college.edu", "Organizer@123")
        bad_times = self.client.post('/api/events', json={
            "event_name": "Backwards Time Event",
            "requested_date": "2026-12-01",
            "requested_start_time": "15:00:00",
            "requested_end_time": "12:00:00"
        })
        self.assertEqual(bad_times.status_code, 400)
        self.assertIn("precede", bad_times.get_json()['message'].lower())

        # 4. Invalid date format
        bad_date = self.client.post('/api/events', json={
            "event_name": "Invalid Date Event",
            "requested_date": "not-a-date",
            "requested_start_time": "10:00:00",
            "requested_end_time": "12:00:00"
        })
        self.assertEqual(bad_date.status_code, 400)
        print("   [OK] TEST 20: Invalid event/venue input rejected correctly (400).")


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStage4VenueEventManagement)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
