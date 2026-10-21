"""
Stage 6 Image Upload & Storage Verification Suite
-------------------------------------------------
Verifies all 15 Acceptance Tests for Stage 6:
  TEST 1:  Authenticated organizer can upload a valid JPG image (HTTP 201).
  TEST 2:  Authenticated organizer can upload a valid PNG image (HTTP 201).
  TEST 3:  Missing file in request is rejected (HTTP 400).
  TEST 4:  Unsupported file extension is rejected (HTTP 400).
  TEST 5:  Oversized image (>10 MB) is rejected (HTTP 400).
  TEST 6:  Invalid/fake image (non-image content) is rejected by validator (HTTP 400).
  TEST 7:  Organizer cannot upload to another organizer's event (HTTP 403).
  TEST 8:  Organizer cannot upload to a pending or rejected event (HTTP 400).
  TEST 9:  Unauthenticated upload request is rejected (HTTP 401).
  TEST 10: Management cannot use organizer upload endpoint (HTTP 403).
  TEST 11: Uploaded image metadata is correctly stored in MySQL.
  TEST 12: Image listing endpoint returns images for the authorized event.
  TEST 13: Organizer cannot retrieve another organizer's image history (HTTP 403).
  TEST 14: Database failure after file save triggers automatic file cleanup (no orphan files).
  TEST 15: Safe image serving endpoint serves uploaded image files correctly (HTTP 200).
"""

import os
import io
import sys
import shutil
import unittest
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from PIL import Image

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.settings import settings
from config.db import check_db_status
import config.db
from middleware.auth import hash_password
from models.image import ImageModel


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


def create_test_image_bytes(fmt='JPEG', size=(80, 80), color=(63, 102, 241)):
    """Creates a real in-memory image for upload testing."""
    buf = io.BytesIO()
    img = Image.new('RGB', size, color=color)
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf


class TestStage6ImageUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Configure test environment and seed test users, venues, events, and images."""
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'stage6-test-secret-key-2026'

        # Use temporary test upload folder
        cls.test_upload_dir = BACKEND_DIR / 'uploads' / 'test_event_images'
        os.makedirs(cls.test_upload_dir, exist_ok=True)
        cls.orig_upload_folder = settings.UPLOAD_FOLDER
        settings.UPLOAD_FOLDER = cls.test_upload_dir

        # Always isolate database to in-memory SQLite
        try:
            from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
        except ImportError:
            from db_guard import IsolatedTestDatabase, install_global_safety_guard
        install_global_safety_guard()

        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.patch_models()
        cls.seed_data()

    @classmethod
    def tearDownClass(cls):
        """Restore settings and cleanup temporary test upload folder."""
        settings.UPLOAD_FOLDER = cls.orig_upload_folder
        if os.path.exists(cls.test_upload_dir):
            shutil.rmtree(cls.test_upload_dir, ignore_errors=True)

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

            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                FOREIGN KEY (organizer_id) REFERENCES users(id),
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );

            CREATE TABLE images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_status TEXT CHECK(processing_status IN ('pending', 'processing', 'completed', 'failed')) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id)
            );

            CREATE TABLE crowd_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                predicted_count INTEGER NOT NULL,
                analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_status TEXT DEFAULT 'completed',
                model_name TEXT DEFAULT 'CSRNet',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id)
            );
        """)
        cls.sqlite_conn.commit()

    @classmethod
    def seed_data(cls):
        conn = config.db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM crowd_analyses;")
                cur.execute("DELETE FROM images;")
                cur.execute("DELETE FROM events;")
                cur.execute("DELETE FROM venues;")
                cur.execute("DELETE FROM users;")

                pw_hash = hash_password("Password123!")

                # Users
                cur.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s);",
                            (1, "Management Admin", "admin@college.edu", pw_hash, "management"))
                cur.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s);",
                            (2, "Organizer Alice", "alice@clubs.edu", pw_hash, "organizer"))
                cur.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s);",
                            (3, "Organizer Bob", "bob@sports.edu", pw_hash, "organizer"))

                # Venues
                cur.execute("INSERT INTO venues (id, name, location, capacity, status) VALUES (%s, %s, %s, %s, %s);",
                            (101, "Main Auditorium", "Block A, 1st Floor", 1000, "available"))

                # Events for Alice:
                # 501: Approved event
                # 502: Pending event
                # 503: Rejected event
                today_str = date.today().isoformat()
                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (501, 2, "Alice Approved TechFest", "Annual tech fest", "approved",
                      today_str, "00:00:00", "23:59:59", today_str, "00:00:00", "23:59:59", 101))

                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (502, 2, "Alice Pending Workshop", "Workshop awaiting review", "pending",
                      today_str, "10:00:00", "13:00:00", None))

                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status, rejection_reason,
                                        requested_date, requested_start_time, requested_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (503, 2, "Alice Rejected Gala", "Denied party", "rejected", "Policy restriction",
                      today_str, "20:00:00", "23:00:00", None))

                # Event for Bob:
                # 601: Approved event for Bob
                cur.execute("""
                    INSERT INTO events (id, organizer_id, event_name, description, status,
                                        requested_date, requested_start_time, requested_end_time,
                                        approved_date, approved_start_time, approved_end_time, venue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (601, 3, "Bob Approved Tournament", "Cricket finals", "approved",
                      today_str, "00:00:00", "23:59:59", today_str, "00:00:00", "23:59:59", 101))
        finally:
            conn.close()

    def setUp(self):
        self.client = self.app.test_client()

    def _login(self, email, password="Password123!"):
        res = self.client.post('/api/auth/login', json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200)

    def _logout(self):
        self.client.post('/api/auth/logout')

    # =========================================================
    # TESTS
    # =========================================================

    def test_01_organizer_can_upload_valid_jpg(self):
        """TEST 1: Authenticated organizer can upload a valid JPG image."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes(fmt='JPEG')

        data = {
            'image': (img_bytes, 'auditorium_photo_01.jpg')
        }
        res = self.client.post('/api/events/501/images', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 201)

        payload = res.get_json()
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("message"), "Image uploaded successfully.")
        img_data = payload.get("image", {})
        self.assertEqual(img_data.get("event_id"), 501)
        self.assertEqual(img_data.get("processing_status"), "pending")
        self.assertIn("uploads/event_images/event_501_", img_data.get("image_path"))

        # Verify physical file was written to disk
        filename = os.path.basename(img_data["image_path"])
        full_path = os.path.join(settings.UPLOAD_FOLDER, filename)
        self.assertTrue(os.path.exists(full_path))
        self._logout()

    def test_02_organizer_can_upload_valid_png(self):
        """TEST 2: Authenticated organizer can upload a valid PNG image."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes(fmt='PNG')

        data = {
            'image': (img_bytes, 'seminar_crowd_02.png')
        }
        res = self.client.post('/api/events/501/images', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 201)

        payload = res.get_json()
        self.assertTrue(payload.get("success"))
        img_data = payload.get("image", {})
        self.assertEqual(img_data.get("event_id"), 501)
        self.assertEqual(img_data.get("processing_status"), "pending")
        self.assertTrue(img_data.get("image_path").endswith(".png"))
        self._logout()

    def test_03_missing_file_is_rejected(self):
        """TEST 3: Missing file in request is rejected with HTTP 400."""
        self._login("alice@clubs.edu")
        res = self.client.post('/api/events/501/images', data={}, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        self.assertIn("Please select an image to upload", res.get_json().get("message", ""))
        self._logout()

    def test_04_unsupported_file_extension_is_rejected(self):
        """TEST 4: Unsupported file extensions (.txt, .exe, .py) are rejected with HTTP 400."""
        self._login("alice@clubs.edu")
        dummy_file = io.BytesIO(b"malicious script payload")

        data = {
            'image': (dummy_file, 'exploit.php')
        }
        res = self.client.post('/api/events/501/images', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported image format", res.get_json().get("message", ""))
        self._logout()

    def test_05_oversized_image_is_rejected(self):
        """TEST 5: File exceeding MAX_CONTENT_LENGTH (10 MB) is rejected with HTTP 400."""
        self._login("alice@clubs.edu")
        # Create oversized mock stream (>10 MB)
        oversized_bytes = io.BytesIO(b"A" * (10 * 1024 * 1024 + 1024))

        data = {
            'image': (oversized_bytes, 'huge_photo.jpg')
        }
        res = self.client.post('/api/events/501/images', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        self.assertIn("exceeds the maximum allowed limit", res.get_json().get("message", ""))
        self._logout()

    def test_06_invalid_image_content_rejected(self):
        """TEST 6: Non-image file renamed to .jpg is rejected by content validation."""
        self._login("alice@clubs.edu")
        # Text file with .jpg extension
        fake_image = io.BytesIO(b"This is plain text pretending to be a JPG photograph.")

        data = {
            'image': (fake_image, 'fake_photo.jpg')
        }
        res = self.client.post('/api/events/501/images', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        self.assertIn("not a valid image", res.get_json().get("message", ""))
        self._logout()

    def test_07_organizer_cannot_upload_to_another_organizers_event(self):
        """TEST 7: Organizer cannot upload images to another organizer's event (HTTP 403)."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes()

        # Alice attempts to upload to Bob's event (601)
        data = {'image': (img_bytes, 'unauthorized_upload.jpg')}
        res = self.client.post('/api/events/601/images', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json().get("error"), "Forbidden")
        self._logout()

    def test_08_cannot_upload_to_pending_or_rejected_event(self):
        """TEST 8: Organizer cannot upload images to pending (502) or rejected (503) events."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes()

        # Pending event (502)
        res_pending = self.client.post('/api/events/502/images',
                                       data={'image': (img_bytes, 'pending_event.jpg')},
                                       content_type='multipart/form-data')
        self.assertEqual(res_pending.status_code, 400)
        self.assertIn("only be uploaded for approved events", res_pending.get_json().get("message", ""))

        # Rejected event (503)
        img_bytes_rejected = create_test_image_bytes()
        res_rejected = self.client.post('/api/events/503/images',
                                        data={'image': (img_bytes_rejected, 'rejected_event.jpg')},
                                        content_type='multipart/form-data')
        self.assertEqual(res_rejected.status_code, 400)
        self.assertIn("only be uploaded for approved events", res_rejected.get_json().get("message", ""))
        self._logout()

    def test_09_unauthenticated_upload_is_rejected(self):
        """TEST 9: Unauthenticated upload request returns HTTP 401."""
        img_bytes = create_test_image_bytes()
        res = self.client.post('/api/events/501/images',
                               data={'image': (img_bytes, 'test.jpg')},
                               content_type='multipart/form-data')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get("error"), "Unauthorized")

    def test_10_management_cannot_use_organizer_upload_endpoint(self):
        """TEST 10: Management role cannot use organizer upload endpoint (HTTP 403)."""
        self._login("admin@college.edu")
        img_bytes = create_test_image_bytes()
        res = self.client.post('/api/events/501/images',
                               data={'image': (img_bytes, 'mgmt_upload.jpg')},
                               content_type='multipart/form-data')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json().get("error"), "Forbidden")
        self._logout()

    def test_11_metadata_correctly_stored_in_database(self):
        """TEST 11: Uploaded image metadata is correctly stored in MySQL."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes()
        res = self.client.post('/api/events/501/images',
                               data={'image': (img_bytes, 'db_verify.jpg')},
                               content_type='multipart/form-data')
        self.assertEqual(res.status_code, 201)
        img_id = res.get_json()["image"]["id"]

        # Verify in DB
        db_img = ImageModel.get_by_id(img_id)
        self.assertIsNotNone(db_img)
        self.assertEqual(db_img["event_id"], 501)
        self.assertEqual(db_img["processing_status"], "pending")
        self.assertIn("uploads/event_images/", db_img["image_path"])
        self.assertIsNotNone(db_img.get("uploaded_at"))
        self._logout()

    def test_12_image_listing_returns_authorized_event_images(self):
        """TEST 12: Image listing endpoint returns images for the authorized event."""
        self._login("alice@clubs.edu")
        res = self.client.get('/api/events/501/images')
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("event_id"), 501)
        images = data.get("images", [])
        self.assertGreaterEqual(len(images), 1)

        # Check item structure
        first = images[0]
        self.assertIn("id", first)
        self.assertEqual(first["event_id"], 501)
        self.assertEqual(first["processing_status"], "pending")
        self.assertIn("/uploads/event_images/", first["image_url"])
        self.assertIsNotNone(first["uploaded_at"])
        self._logout()

    def test_13_organizer_cannot_retrieve_another_organizers_image_history(self):
        """TEST 13: Organizer cannot retrieve another organizer's image history (HTTP 403)."""
        self._login("alice@clubs.edu")
        # Alice tries to list images for Bob's event (601)
        res = self.client.get('/api/events/601/images')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json().get("error"), "Forbidden")
        self._logout()

    def test_14_database_failure_cleans_up_saved_file(self):
        """TEST 14: Database failure after file save does not leave an orphan file."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes()

        # Monkeypatch create_image to simulate a database failure
        orig_create = ImageModel.create_image
        try:
            def failing_create(*args, **kwargs):
                raise RuntimeError("Simulated database constraint failure")

            ImageModel.create_image = failing_create

            # Snapshot files in upload folder before upload
            before_files = set(os.listdir(settings.UPLOAD_FOLDER))

            res = self.client.post('/api/events/501/images',
                                   data={'image': (img_bytes, 'rollback_test.jpg')},
                                   content_type='multipart/form-data')
            self.assertEqual(res.status_code, 500)

            # Check that no new orphan file was left in the folder
            after_files = set(os.listdir(settings.UPLOAD_FOLDER))
            self.assertEqual(before_files, after_files, "Orphan file was found after DB failure rollback!")
        finally:
            ImageModel.create_image = orig_create
            self._logout()

    def test_15_safe_image_serving_endpoint(self):
        """TEST 15: Safe image serving endpoint serves uploaded image files correctly (HTTP 200)."""
        self._login("alice@clubs.edu")
        img_bytes = create_test_image_bytes()
        res_upload = self.client.post('/api/events/501/images',
                                      data={'image': (img_bytes, 'serve_test.jpg')},
                                      content_type='multipart/form-data')
        self.assertEqual(res_upload.status_code, 201)
        image_url = res_upload.get_json()["image"]["image_url"]

        # Fetch the image directly
        res_img = self.client.get(image_url)
        self.assertEqual(res_img.status_code, 200)
        self.assertIn("image/", res_img.content_type)
        self.assertGreater(len(res_img.data), 0)
        self._logout()


if __name__ == '__main__':
    unittest.main(verbosity=2)
