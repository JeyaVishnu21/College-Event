"""
Stage 5 Dashboards Verification Suite
-------------------------------------
Verifies real database calculations, role-based isolation, dynamic metrics,
and security enforcement for Organizer and Management dashboards.

Acceptance Tests:
  TEST 1:  Organizer can access their dashboard and receive real database statistics.
  TEST 2:  Organizer dashboard returns only the authenticated organizer's events (Isolation).
  TEST 3:  Creating an event dynamically increments organizer total and pending statistics.
  TEST 4:  Management can access system-wide dashboard and receive real aggregated statistics.
  TEST 5:  Management dashboard includes pending requests, upcoming events, and campus venues.
  TEST 6:  Approving an event dynamically updates pending and approved counts in real time.
  TEST 7:  Venue status changes dynamically update available and unavailable counts.
  TEST 8:  Unauthenticated request to organizer dashboard is rejected (HTTP 401).
  TEST 9:  Unauthenticated request to management dashboard is rejected (HTTP 401).
  TEST 10: Organizer attempting to access management dashboard is rejected (HTTP 403).
  TEST 11: Management attempting to access organizer dashboard is rejected (HTTP 403).
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


try:
    from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
except ImportError:
    from db_guard import IsolatedTestDatabase, install_global_safety_guard

install_global_safety_guard()


class TestStage5Dashboards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Configure isolated in-memory test database and seed test users, venues, and events."""
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

        # Always isolate to an in-memory SQLite database
        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.patch_models()
        cls.seed_data()

    @classmethod
    def tearDownClass(cls):
        """Restore monkeypatched connection functions."""
        if hasattr(cls, 'isolated_db'):
            cls.isolated_db.restore_models()

    @classmethod
    def init_sqlite_schema(cls):
        cur = cls.sqlite_conn.cursor()
        cur.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT CHECK(role IN ('administrator', 'management', 'organizer')) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                status TEXT CHECK(status IN ('available', 'unavailable')) DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE event_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER,
                organizer_id INTEGER NOT NULL,
                venue_id INTEGER,
                event_name TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending', 'approved', 'rejected', 'completed', 'cancelled')) DEFAULT 'pending',
                rejection_reason TEXT,
                requested_date DATE NOT NULL,
                requested_start_time TIME NOT NULL,
                requested_end_time TIME NOT NULL,
                approved_date DATE,
                approved_start_time TIME,
                approved_end_time TIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (series_id) REFERENCES event_series(id),
                FOREIGN KEY (organizer_id) REFERENCES users(id),
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );
        """)
        cls.sqlite_conn.commit()

    @classmethod
    def seed_data(cls):
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Clear existing
                cur.execute("DELETE FROM events;")
                cur.execute("DELETE FROM event_series;")
                cur.execute("DELETE FROM venues;")
                cur.execute("DELETE FROM users;")

                future_date = (date.today() + timedelta(days=7)).isoformat()
                cur.execute("""
                    INSERT INTO event_series (id, name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s);
                """, (1, "Campus Fest", "Annual festival", future_date, future_date))

                pw_hash = hash_password("Password123!")

                # Seed users
                cur.execute("""
                    INSERT INTO users (id, name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s);
                """, (1, "Campus Admin", "admin@campus.edu", pw_hash, "management"))

                cur.execute("""
                    INSERT INTO users (id, name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s);
                """, (2, "Organizer Alice", "alice@clubs.edu", pw_hash, "organizer"))

                cur.execute("""
                    INSERT INTO users (id, name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s);
                """, (3, "Organizer Bob", "bob@sports.edu", pw_hash, "organizer"))

                # Seed venues (2 available, 1 unavailable)
                cur.execute("""
                    INSERT INTO venues (id, name, location, capacity, status)
                    VALUES (%s, %s, %s, %s, %s);
                """, (101, "Main Auditorium", "Central Quad", 500, "available"))

                cur.execute("""
                    INSERT INTO venues (id, name, location, capacity, status)
                    VALUES (%s, %s, %s, %s, %s);
                """, (102, "Seminar Hall A", "Tech Tower", 120, "available"))

                cur.execute("""
                    INSERT INTO venues (id, name, location, capacity, status)
                    VALUES (%s, %s, %s, %s, %s);
                """, (103, "Open Amphitheatre", "West Lawn", 800, "unavailable"))

                # Seed events for Alice (Organizer 2):
                # 1 Pending, 1 Approved (Upcoming), 1 Rejected
                future_date = (date.today() + timedelta(days=7)).isoformat()
                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (201, 2, "AI Hackathon", "Coding marathon", "pending", future_date, "09:00:00", "17:00:00", 101))

                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (202, 2, "Robotics Expo", "Exhibition", "approved", future_date, "10:00:00", "14:00:00",
                      future_date, "10:00:00", "14:00:00", 102))

                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status, rejection_reason,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (203, 2, "Late Night DJ", "Music party", "rejected", "Policy restriction on night events",
                      future_date, "20:00:00", "23:30:00", 101))

                # Seed events for Bob (Organizer 3):
                # 1 Pending
                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (301, 3, "Inter-College Cricket", "Sports tourney", "pending", future_date, "08:00:00", "16:00:00", None))
        finally:
            conn.close()

    def login(self, email, password="Password123!"):
        return self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })

    def logout(self):
        return self.client.post('/api/auth/logout')

    # =========================================================
    # TESTS
    # =========================================================

    def test_01_organizer_dashboard_real_statistics(self):
        """TEST 1: Organizer can access dashboard and receives real calculated database statistics."""
        self.login("alice@clubs.edu")
        res = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("role"), "organizer")

        stats = data.get("stats", {})
        # Alice has 3 events: 1 pending, 1 approved (upcoming), 1 rejected
        self.assertEqual(stats.get("total_events"), 3)
        self.assertEqual(stats.get("pending_events"), 1)
        self.assertEqual(stats.get("approved_events"), 1)
        self.assertEqual(stats.get("rejected_events"), 1)
        self.assertEqual(stats.get("upcoming_events"), 1)
        self.logout()

    def test_02_organizer_dashboard_strict_isolation(self):
        """TEST 2: Organizer dashboard strictly isolates events per authenticated organizer."""
        # Alice's view
        self.login("alice@clubs.edu")
        res_alice = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res_alice.status_code, 200)
        alice_data = res_alice.get_json()
        alice_event_ids = [e['id'] for e in alice_data.get("events", [])]
        self.assertIn(201, alice_event_ids)
        self.assertIn(202, alice_event_ids)
        self.assertNotIn(301, alice_event_ids)  # Bob's event must NOT appear
        self.logout()

        # Bob's view
        self.login("bob@sports.edu")
        res_bob = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res_bob.status_code, 200)
        bob_data = res_bob.get_json()
        bob_event_ids = [e['id'] for e in bob_data.get("events", [])]
        self.assertIn(301, bob_event_ids)
        self.assertNotIn(201, bob_event_ids)  # Alice's events must NOT appear
        # Bob has 1 event: 1 pending, 0 approved, 0 rejected
        self.assertEqual(bob_data.get("stats", {}).get("total_events"), 1)
        self.assertEqual(bob_data.get("stats", {}).get("pending_events"), 1)
        self.assertEqual(bob_data.get("stats", {}).get("approved_events"), 0)
        self.logout()

    def test_03_creating_event_dynamically_increments_stats(self):
        """TEST 3: Creating an event dynamically updates the organizer's database stats."""
        self.login("bob@sports.edu")

        # Initial Bob stats: 1 total, 1 pending
        res_before = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res_before.get_json()["stats"]["total_events"], 1)

        # Create a second event for Bob
        future_date = (date.today() + timedelta(days=14)).isoformat()
        create_res = self.client.post('/api/events', json={
            "series_id": 1,
            "event_name": "Football Championship",
            "description": "Annual tournament",
            "requested_date": future_date,
            "requested_start_time": "14:00:00",
            "requested_end_time": "18:00:00",
            "venue_id": 101
        })
        self.assertEqual(create_res.status_code, 201)

        # Re-fetch Bob dashboard: now 2 total, 2 pending
        res_after = self.client.get('/api/organizer/dashboard')
        stats = res_after.get_json()["stats"]
        self.assertEqual(stats["total_events"], 2)
        self.assertEqual(stats["pending_events"], 2)

        self.logout()

    def test_04_management_dashboard_system_wide_stats(self):
        """TEST 4: Management dashboard returns system-wide real calculated statistics."""
        self.login("admin@campus.edu")
        res = self.client.get('/api/management/dashboard')
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("role"), "management")

        stats = data.get("stats", {})
        # Alice has 3 events, Bob has 2 events => Total: 5 events
        # Pending: Alice(1) + Bob(2) = 3
        # Approved: Alice(1) = 1
        # Rejected: Alice(1) = 1
        self.assertEqual(stats.get("total_events"), 5)
        self.assertEqual(stats.get("pending_requests"), 3)
        self.assertEqual(stats.get("approved_events"), 1)
        self.assertEqual(stats.get("rejected_events"), 1)

        # Venues: Total 3, Available 2, Unavailable 1
        self.assertEqual(stats.get("total_venues"), 3)
        self.assertEqual(stats.get("available_venues"), 2)
        self.assertEqual(stats.get("unavailable_venues"), 1)

        self.logout()

    def test_05_management_dashboard_payload_subsections(self):
        """TEST 5: Management dashboard includes pending requests, upcoming events, and venues list."""
        self.login("admin@campus.edu")
        res = self.client.get('/api/management/dashboard')
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        pending = data.get("pending_requests", [])
        upcoming = data.get("upcoming_events", [])
        venues = data.get("venues", [])

        # Pending contains 3 requests (Alice's Hackathon, Bob's Cricket, Bob's Football)
        self.assertEqual(len(pending), 3)
        pending_names = [p['event_name'] for p in pending]
        self.assertIn("AI Hackathon", pending_names)
        self.assertIn("Inter-College Cricket", pending_names)
        self.assertIn("Football Championship", pending_names)

        # Upcoming contains 1 approved event (Robotics Expo)
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]["event_name"], "Robotics Expo")
        self.assertEqual(upcoming[0]["status"], "approved")

        # Venues list contains 3 venues
        self.assertEqual(len(venues), 3)

        self.logout()

    def test_06_approving_event_dynamically_updates_counts(self):
        """TEST 6: Approving an event shifts pending count to approved count in real time."""
        self.login("admin@campus.edu")

        # Allocate and approve event 201 (AI Hackathon)
        future_date = (date.today() + timedelta(days=7)).isoformat()
        alloc_res = self.client.patch('/api/management/events/201/allocation', json={
            "venue_id": 101,
            "approved_date": future_date,
            "approved_start_time": "09:00:00",
            "approved_end_time": "17:00:00"
        })
        self.assertEqual(alloc_res.status_code, 200)

        # Verify management dashboard counts update: pending: 3 -> 2, approved: 1 -> 2
        mgmt_res = self.client.get('/api/management/dashboard')
        mgmt_stats = mgmt_res.get_json()["stats"]
        self.assertEqual(mgmt_stats["pending_requests"], 2)
        self.assertEqual(mgmt_stats["approved_events"], 2)
        self.assertEqual(mgmt_stats["upcoming_events"], 2)
        self.logout()

        # Verify Alice's organizer dashboard updates: pending: 1 -> 0, approved: 1 -> 2
        self.login("alice@clubs.edu")
        alice_res = self.client.get('/api/organizer/dashboard')
        alice_stats = alice_res.get_json()["stats"]
        self.assertEqual(alice_stats["pending_events"], 0)
        self.assertEqual(alice_stats["approved_events"], 2)
        self.logout()

    def test_07_venue_status_change_dynamically_updates_stats(self):
        """TEST 7: Toggling venue status dynamically reflects in venue summary metrics."""
        self.login("admin@campus.edu")

        # Initially: Total 3, Available 2, Unavailable 1
        dash_1 = self.client.get('/api/management/dashboard').get_json()["stats"]
        self.assertEqual(dash_1["available_venues"], 2)
        self.assertEqual(dash_1["unavailable_venues"], 1)

        # Mark Venue 102 as unavailable
        status_res = self.client.patch('/api/venues/102/status', json={"status": "unavailable"})
        self.assertEqual(status_res.status_code, 200)

        # Re-check: Available 2 -> 1, Unavailable 1 -> 2
        dash_2 = self.client.get('/api/management/dashboard').get_json()["stats"]
        self.assertEqual(dash_2["available_venues"], 1)
        self.assertEqual(dash_2["unavailable_venues"], 2)

        # Restore Venue 102
        self.client.patch('/api/venues/102/status', json={"status": "available"})
        self.logout()

    def test_08_unauthenticated_organizer_dashboard_rejected(self):
        """TEST 8: Unauthenticated access to organizer dashboard returns HTTP 401."""
        res = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get("error"), "Unauthorized")

    def test_09_unauthenticated_management_dashboard_rejected(self):
        """TEST 9: Unauthenticated access to management dashboard returns HTTP 401."""
        res = self.client.get('/api/management/dashboard')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get("error"), "Unauthorized")

    def test_10_organizer_accessing_management_dashboard_forbidden(self):
        """TEST 10: Organizer role attempting to access management dashboard returns HTTP 403."""
        self.login("alice@clubs.edu")
        res = self.client.get('/api/management/dashboard')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json().get("error"), "Forbidden")
        self.logout()

    def test_11_management_accessing_organizer_dashboard_forbidden(self):
        """TEST 11: Management role attempting to access organizer dashboard returns HTTP 403."""
        self.login("admin@campus.edu")
        res = self.client.get('/api/organizer/dashboard')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json().get("error"), "Forbidden")
        self.logout()


if __name__ == '__main__':
    unittest.main(verbosity=2)
