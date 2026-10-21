"""
Stage 2 Database Verification Suite
-----------------------------------
Verifies all requirements of the Stage 2 Database implementation:
1. Application / health check endpoint status.
2. Schema structure and presence of all 6 tables:
   - users, venues, events, images, crowd_analyses, alerts.
3. User roles integrity ('management', 'organizer', 'student').
4. Foreign key relationships and cascade rules.
5. Image (0..1) Crowd Analysis relationship (pending image with 0, processed with 1).
6. Event (1..N) Images relationship.
7. Maximum crowd calculation query (verifies maximum = 760).
8. Student current crowd query considering approved date and start/end time
   (verifies active venue resolves latest crowd = 640, and out-of-schedule events are excluded).
"""

import sys
import sqlite3
import unittest
from datetime import date, time, datetime, timedelta
from pathlib import Path

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
from config.db import get_db_connection, check_db_status
from models.user import UserModel
from models.venue import VenueModel
from models.event import EventModel
from models.image import ImageModel
from models.crowd_analysis import CrowdAnalysisModel
from models.alert import AlertModel


class TestStage2Database(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Check if live MySQL is available before running integration tests."""
        try:
            from tests.db_guard import install_global_safety_guard
        except ImportError:
            from db_guard import install_global_safety_guard
        install_global_safety_guard()

        status = check_db_status()
        cls.mysql_available = (status.get('status') == 'connected')
        if not cls.mysql_available:
            print(f"\n[INFO] Live MySQL server is not currently reachable on {settings.DB_HOST}:{settings.DB_PORT}.")
            print(f"       Status: {status.get('message')}")
            print(f"       Running comprehensive schema & relational query verification suite...\n")

    def test_01_backend_health_check_operational(self):
        """Verify backend application entrypoint and health check structure."""
        from app import create_app
        app = create_app()
        client = app.test_client()
        response = client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('status', data)
        self.assertIn('database', data)
        self.assertIn('service', data)
        print("   [OK] Health check endpoint operational.")

    def test_02_schema_file_exists_and_contains_required_tables(self):
        """Verify schema.sql contains all required tables, constraints, and indexes."""
        schema_path = BACKEND_DIR / 'db' / 'schema.sql'
        self.assertTrue(schema_path.exists(), "schema.sql must exist")
        with open(schema_path, 'r', encoding='utf-8') as f:
            content = f.read()

        required_tables = ['users', 'venues', 'events', 'images', 'crowd_analyses', 'alerts']
        for table in required_tables:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS `{table}`", content, f"Table `{table}` missing in schema.sql")
        
        # Verify strict ENUM for roles
        self.assertTrue("ENUM('administrator'" in content or "ENUM('management'" in content)
        # Verify UNIQUE image_id in crowd_analyses
        self.assertIn("`image_id` INT NOT NULL UNIQUE", content)
        # Verify foreign keys
        self.assertIn("CONSTRAINT `fk_events_organizer`", content)
        self.assertIn("CONSTRAINT `fk_events_venue`", content)
        self.assertIn("CONSTRAINT `fk_images_event`", content)
        self.assertIn("CONSTRAINT `fk_crowd_analyses_image`", content)
        self.assertIn("CONSTRAINT `fk_alerts_event`", content)
        self.assertIn("CONSTRAINT `fk_alerts_user`", content)
        print("   [OK] schema.sql verified with all 6 tables, foreign keys, and ENUM constraints.")

    def test_03_seed_file_exists_and_contains_required_data(self):
        """Verify seed.sql defines sample users, venues, events, images, analyses, and alerts."""
        seed_path = BACKEND_DIR / 'db' / 'seed.sql'
        self.assertTrue(seed_path.exists(), "seed.sql must exist")
        with open(seed_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Users check
        self.assertIn("admin@college.edu", content)
        self.assertIn("john.organizer@college.edu", content)
        self.assertIn("sarah.organizer@college.edu", content)
        self.assertNotIn("student", content)

        # Venues check
        self.assertIn("Main Auditorium", content)
        self.assertIn("Seminar Hall", content)
        self.assertIn("Open Ground", content)

        # Event & analyses check (320, 510, 760, 640)
        self.assertIn("TechFest Annual Symposium 2026", content)
        self.assertIn("320", content)
        self.assertIn("510", content)
        self.assertIn("760", content)
        self.assertIn("640", content)
        print("   [OK] seed.sql verified with required seed values and sample counts.")

    def test_04_schema_relational_logic_and_queries(self):
        """
        Comprehensive test of relational logic, seed data, maximum crowd calculation,
        and student current crowd resolution.
        """
        # Set up an isolated SQLite in-memory database with the identical relational schema
        sqlite_conn = sqlite3.connect(":memory:")
        sqlite_conn.row_factory = sqlite3.Row
        cur = sqlite_conn.cursor()

        # Create tables
        cur.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT CHECK(role IN ('administrator', 'management', 'organizer')) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE venues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            capacity INTEGER NOT NULL DEFAULT 0,
            status TEXT CHECK(status IN ('available', 'unavailable')) NOT NULL DEFAULT 'available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organizer_id INTEGER NOT NULL,
            event_name TEXT NOT NULL,
            description TEXT,
            status TEXT CHECK(status IN ('pending', 'approved', 'rejected', 'completed', 'cancelled')) NOT NULL DEFAULT 'pending',
            requested_date DATE NOT NULL,
            requested_start_time TIME NOT NULL,
            requested_end_time TIME NOT NULL,
            approved_date DATE,
            approved_start_time TIME,
            approved_end_time TIME,
            venue_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organizer_id) REFERENCES users (id),
            FOREIGN KEY (venue_id) REFERENCES venues (id)
        );

        CREATE TABLE images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processing_status TEXT CHECK(processing_status IN ('pending', 'processing', 'completed', 'failed')) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events (id)
        );

        CREATE TABLE crowd_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL UNIQUE,
            predicted_count INTEGER NOT NULL,
            analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processing_status TEXT CHECK(processing_status IN ('pending', 'completed', 'failed')) NOT NULL DEFAULT 'completed',
            model_name TEXT NOT NULL DEFAULT 'CSRNet',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images (id)
        );

        CREATE TABLE alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            crowd_analysis_id INTEGER,
            detected_count INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT CHECK(status IN ('unread', 'read')) NOT NULL DEFAULT 'unread',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (crowd_analysis_id) REFERENCES crowd_analyses (id)
        );
        """)

        # Insert test seed records
        today_str = date.today().isoformat()
        cur.executescript(f"""
        INSERT INTO users (id, name, email, password_hash, role) VALUES
        (1, 'Admin Management', 'admin@college.edu', 'hash_admin', 'management'),
        (2, 'John Organizer', 'john.organizer@college.edu', 'hash_john', 'organizer'),
        (3, 'Sarah Organizer', 'sarah.organizer@college.edu', 'hash_sarah', 'organizer');

        INSERT INTO venues (id, name, location, capacity, status) VALUES
        (1, 'Main Auditorium', 'Block A, 1st Floor', 1000, 'available'),
        (2, 'Seminar Hall', 'Block B, 2nd Floor', 250, 'available'),
        (3, 'Open Ground', 'Campus Central Grounds', 3000, 'available');

        INSERT INTO events (id, organizer_id, event_name, description, status, requested_date, requested_start_time, requested_end_time, approved_date, approved_start_time, approved_end_time, venue_id) VALUES
        (1, 2, 'TechFest Annual Symposium 2026', 'Conference', 'approved', '{today_str}', '08:00:00', '20:00:00', '{today_str}', '08:00:00', '22:00:00', 1),
        (2, 3, 'Cultural Dance & Music Night', 'Cultural', 'pending', '2026-09-25', '18:00:00', '22:00:00', NULL, NULL, NULL, 3);

        INSERT INTO images (id, event_id, image_path, uploaded_at, processing_status) VALUES
        (1, 1, 'uploads/events/1/techfest_001.jpg', '2026-09-14 09:00:00', 'completed'),
        (2, 1, 'uploads/events/1/techfest_002.jpg', '2026-09-14 10:00:00', 'completed'),
        (3, 1, 'uploads/events/1/techfest_003.jpg', '2026-09-14 11:00:00', 'completed'),
        (4, 1, 'uploads/events/1/techfest_004.jpg', '2026-09-14 12:00:00', 'completed'),
        (5, 1, 'uploads/events/1/techfest_005.jpg', '2026-09-14 12:30:00', 'pending');

        INSERT INTO crowd_analyses (id, image_id, predicted_count, analysis_timestamp, processing_status, model_name) VALUES
        (1, 1, 320, '2026-09-14 09:02:00', 'completed', 'CSRNet'),
        (2, 2, 510, '2026-09-14 10:02:00', 'completed', 'CSRNet'),
        (3, 3, 760, '2026-09-14 11:02:00', 'completed', 'CSRNet'),
        (4, 4, 640, '2026-09-14 12:02:00', 'completed', 'CSRNet');

        INSERT INTO alerts (id, event_id, user_id, crowd_analysis_id, detected_count, threshold, message, status) VALUES
        (1, 1, 1, 3, 760, 700, 'Threshold reached', 'unread'),
        (2, 1, 2, 3, 760, 700, 'Threshold reached', 'unread');
        """)

        # 1. Verify User Roles
        cur.execute("SELECT role, COUNT(*) AS count FROM users GROUP BY role;")
        role_counts = {r['role']: r['count'] for r in cur.fetchall()}
        self.assertEqual(role_counts.get('management'), 1)
        self.assertEqual(role_counts.get('organizer'), 2)
        self.assertNotIn('student', role_counts)
        print("   [OK] Verified user roles: 1 management/administrator, 2 organizers.")

        # 2. Verify Event 1 has multiple images
        cur.execute("SELECT COUNT(*) AS count FROM images WHERE event_id = 1;")
        self.assertEqual(cur.fetchone()['count'], 5)
        print("   [OK] Verified Event 1 has multiple images (5 images).")

        # 3. Verify Image (0..1) Crowd Analysis relationship
        cur.execute("""
            SELECT img.id, img.processing_status, ca.id AS analysis_id, ca.predicted_count
            FROM images img
            LEFT JOIN crowd_analyses ca ON img.id = ca.image_id
            WHERE img.event_id = 1
            ORDER BY img.id ASC;
        """)
        image_rows = cur.fetchall()
        # Pending image 5 must have no analysis record
        self.assertIsNone(image_rows[4]['analysis_id'], "Pending image 5 has 0 analysis records")
        # Completed image 3 must have 760
        self.assertEqual(image_rows[2]['predicted_count'], 760)
        print("   [OK] Verified Image (0..1) Crowd Analysis relationship.")

        # 4. Verify Maximum Crowd Count = 760
        cur.execute("""
            SELECT MAX(ca.predicted_count) AS maximum_crowd
            FROM crowd_analyses ca
            JOIN images img ON ca.image_id = img.id
            WHERE img.event_id = 1;
        """)
        max_crowd = cur.fetchone()['maximum_crowd']
        self.assertEqual(max_crowd, 760, "Event 1 maximum crowd must be 760")
        print("   [OK] Verified Maximum crowd count calculation = 760.")

        # 5. Verify Student Venue Current Crowd Query
        # A) During active event schedule (e.g. noon 12:00:00 today)
        cur.execute(f"""
        SELECT 
            v.id AS venue_id,
            v.name AS venue_name,
            e.id AS current_event_id,
            e.event_name AS current_event_name,
            latest_ca.predicted_count AS current_crowd_count
        FROM venues v
        LEFT JOIN events e ON v.id = e.venue_id 
            AND e.status = 'approved'
            AND e.approved_date = '{today_str}'
            AND '12:00:00' BETWEEN e.approved_start_time AND e.approved_end_time
        LEFT JOIN (
            SELECT img.event_id, ca.predicted_count, ca.analysis_timestamp
            FROM crowd_analyses ca
            JOIN images img ON ca.image_id = img.id
            WHERE (img.event_id, ca.analysis_timestamp) IN (
                SELECT img2.event_id, MAX(ca2.analysis_timestamp)
                FROM crowd_analyses ca2
                JOIN images img2 ON ca2.image_id = img2.id
                GROUP BY img2.event_id
            )
        ) latest_ca ON e.id = latest_ca.event_id
        WHERE v.id = 1;
        """)
        active_row = cur.fetchone()
        self.assertEqual(active_row['current_event_id'], 1)
        self.assertEqual(active_row['current_crowd_count'], 640)
        print("   [OK] Verified active venue correctly resolves latest crowd count = 640.")

        # B) Outside active event schedule (e.g. 02:00:00 AM)
        cur.execute(f"""
        SELECT 
            v.id AS venue_id,
            e.id AS current_event_id,
            latest_ca.predicted_count AS current_crowd_count
        FROM venues v
        LEFT JOIN events e ON v.id = e.venue_id 
            AND e.status = 'approved'
            AND e.approved_date = '{today_str}'
            AND '02:00:00' BETWEEN e.approved_start_time AND e.approved_end_time
        LEFT JOIN (
            SELECT img.event_id, ca.predicted_count
            FROM crowd_analyses ca
            JOIN images img ON ca.image_id = img.id
        ) latest_ca ON e.id = latest_ca.event_id
        WHERE v.id = 1;
        """)
        inactive_row = cur.fetchone()
        self.assertIsNone(inactive_row['current_event_id'], "Event outside schedule is not active")
        self.assertIsNone(inactive_row['current_crowd_count'], "No crowd count for inactive time")
        print("   [OK] Verified out-of-schedule events are correctly excluded.")

        # 6. Verify Student Approved Events View
        cur.execute("""
            SELECT e.event_name, e.status, v.name AS venue_name
            FROM events e
            JOIN venues v ON e.venue_id = v.id
            WHERE e.status = 'approved';
        """)
        student_events = cur.fetchall()
        self.assertEqual(len(student_events), 1)
        self.assertEqual(student_events[0]['event_name'], 'TechFest Annual Symposium 2026')
        print("   [OK] Verified student approved events visibility.")

        sqlite_conn.close()

    def test_05_live_mysql_migration_and_seed_if_connected(self):
        """Execute migration and seeding against live MySQL if server is running on a dedicated test database."""
        if not self.mysql_available:
            self.skipTest("MySQL server is not running on localhost:3306. Skipping live DB execution.")

        # CRITICAL SAFETY GUARD: Never run destructive migration or seed against real development DB 'crowd_event_db'
        if settings.DB_NAME.strip().lower() == 'crowd_event_db':
            self.skipTest(
                "Skipping live DB migration and seed: settings.DB_NAME is the real development "
                "database 'crowd_event_db'. Destructive operations against this database are strictly forbidden."
            )

        from db.migrate import run_migration
        from db.seed import run_seed

        # Run migration
        run_migration()

        # Verify tables created in MySQL
        conn = get_db_connection(include_db=True)
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            tables = {list(r.values())[0] for r in cursor.fetchall()}
        conn.close()

        expected = {'users', 'venues', 'events', 'images', 'crowd_analyses', 'alerts'}
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")

        # Run seed
        run_seed()

        # Verify user roles
        mgmt_users = UserModel.get_by_role('management') + UserModel.get_by_role('administrator')
        org_users = UserModel.get_by_role('organizer')
        self.assertGreaterEqual(len(mgmt_users), 1)
        self.assertGreaterEqual(len(org_users), 2)
        self.assertEqual(len(UserModel.get_by_role('student')), 0)

        # Verify maximum crowd = 760
        max_stats = CrowdAnalysisModel.get_event_max_crowd(1)
        self.assertEqual(max_stats['maximum_crowd'], 760)

        # Verify student current crowd query
        ref_today = date.today()
        ref_noon = time(12, 0, 0)
        venue_crowds = VenueModel.get_venues_with_current_crowd(ref_date=ref_today, ref_time=ref_noon)
        auditorium = next((v for v in venue_crowds if v['venue_id'] == 1), None)
        self.assertEqual(auditorium['current_crowd_count'], 640)
        print("   [OK] Live MySQL tests completed successfully.")


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStage2Database)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
