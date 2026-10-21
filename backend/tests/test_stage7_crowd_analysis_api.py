"""
Stage 7 Crowd Analysis API Integration Verification Suite
-----------------------------------------------------------
Verifies the integration of CSRNet crowd estimation with the Flask backend:
  TEST 1:  Authenticated organizer can analyze their own approved event image (HTTP 200).
  TEST 2:  Authenticated administrator can analyze any event image (HTTP 200).
  TEST 3:  Unauthenticated request is rejected (HTTP 401).
  TEST 4:  Organizer cannot analyze another organizer's event image (HTTP 403).
  TEST 5:  Non-existent image returns HTTP 404 Not Found.
  TEST 6:  Mismatched event ID returns HTTP 400 Bad Request.
  TEST 7:  Image for pending/rejected event returns HTTP 400 Bad Request.
  TEST 8:  Missing image file on storage returns HTTP 404 and marks image as failed.
  TEST 9:  Corrupted image file on storage returns HTTP 422 and marks image as failed.
  TEST 10: Repeated/duplicate analysis request safely updates existing record (upsert).
  TEST 11: GET /api/images/<image_id>/analysis returns analysis record (HTTP 200).
  TEST 12: GET /api/images/<image_id>/analysis enforces role authorization (HTTP 403).
  TEST 13: GET /api/images/<image_id>/analysis returns 404 when not analyzed.
  TEST 14: Model inference failure returns safe HTTP 500 without leaking stack traces.
  TEST 15: Real end-to-end inference executes and persists correctly.
"""

import os
import io
import sys
import shutil
import unittest
from unittest.mock import patch
from datetime import date, timedelta
from pathlib import Path
from PIL import Image

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.settings import settings
from middleware.auth import hash_password
from models.image import ImageModel
from models.crowd_analysis import CrowdAnalysisModel
from routes.images import is_blank_or_uniform_image

try:
    from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
except ImportError:
    from db_guard import IsolatedTestDatabase, install_global_safety_guard

install_global_safety_guard()


def create_test_image_file(folder: Path, filename: str, size=(160, 120), color=(120, 150, 180), is_solid: bool = False):
    """Creates a real image file on disk in the test upload directory."""
    filepath = folder / filename
    img = Image.new('RGB', size, color=color)
    if not is_solid:
        # Add non-uniform features so normal test images simulate real, non-blank photographs
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 60, 60], fill=(240, 200, 100))
        draw.line([0, 0, size[0], size[1]], fill=(10, 20, 30), width=2)
    img.save(filepath, format='JPEG')
    return filepath


class TestStage7CrowdAnalysisAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Configure test environment, isolate SQLite DB, and seed test data."""
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'stage7-test-secret-key-2026'

        # Use isolated test uploads directory
        cls.test_upload_dir = BACKEND_DIR / 'uploads' / 'test_stage7_analysis'
        os.makedirs(cls.test_upload_dir, exist_ok=True)
        cls.orig_upload_folder = settings.UPLOAD_FOLDER
        settings.UPLOAD_FOLDER = cls.test_upload_dir

        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.patch_models()
        cls.seed_data()

    @classmethod
    def tearDownClass(cls):
        """Restore configuration, cleanup files, and restore database."""
        settings.UPLOAD_FOLDER = cls.orig_upload_folder
        if os.path.exists(cls.test_upload_dir):
            shutil.rmtree(cls.test_upload_dir, ignore_errors=True)
        if hasattr(cls, 'isolated_db'):
            cls.isolated_db.restore_models()

    @classmethod
    def seed_data(cls):
        """Seed users, venues, events, and image records in test database."""
        cur = cls.sqlite_conn.cursor()
        admin_hash = hash_password("Admin@123")
        org1_hash = hash_password("Org1@123")
        org2_hash = hash_password("Org2@123")

        # 1. Users
        cur.executemany("""
            INSERT OR REPLACE INTO users (id, name, email, password_hash, role)
            VALUES (?, ?, ?, ?, ?);
        """, [
            (1, "Admin User", "admin@test.edu", admin_hash, "administrator"),
            (2, "Organizer One", "org1@test.edu", org1_hash, "organizer"),
            (3, "Organizer Two", "org2@test.edu", org2_hash, "organizer"),
        ])

        # 2. Venues
        cur.executemany("""
            INSERT OR REPLACE INTO venues (id, name, location, capacity, status)
            VALUES (?, ?, ?, ?, ?);
        """, [
            (1, "Main Arena", "Zone A", 2000, "available")
        ])

        # 3. Events
        # Event 101: Approved event owned by Organizer 1
        # Event 102: Approved event owned by Organizer 2
        # Event 103: Pending event owned by Organizer 1
        today = date.today().isoformat()
        cur.executemany("""
            INSERT OR REPLACE INTO events (
                id, organizer_id, venue_id, event_name, status,
                requested_date, requested_start_time, requested_end_time,
                approved_date, approved_start_time, approved_end_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [
            (101, 2, 1, "TechFest Opening", "approved", today, "10:00:00", "14:00:00", today, "10:00:00", "14:00:00"),
            (102, 3, 1, "Cultural Gala", "approved", today, "15:00:00", "19:00:00", today, "15:00:00", "19:00:00"),
            (103, 2, 1, "Robotics Workshop", "pending", today, "11:00:00", "13:00:00", None, None, None)
        ])

        # 4. Images on disk and in database
        # Image 201: valid image for Event 101
        create_test_image_file(cls.test_upload_dir, "event_101_img_201.jpg")
        # Image 202: valid image for Event 102
        create_test_image_file(cls.test_upload_dir, "event_102_img_202.jpg")
        # Image 203: valid image for Pending Event 103
        create_test_image_file(cls.test_upload_dir, "event_103_img_203.jpg")
        # Image 206: unanalyzed image for Event 102
        create_test_image_file(cls.test_upload_dir, "event_102_img_206.jpg")
        # Image 207: solid-color uniform image for Event 101 (should be rejected)
        create_test_image_file(cls.test_upload_dir, "event_101_solid_207.jpg", is_solid=True)
        # Image 208: solid-color uniform image for Event 101 with an existing completed analysis
        create_test_image_file(cls.test_upload_dir, "event_101_overwrite_208.jpg", is_solid=True)
        # Image 204: database entry pointing to non-existent file
        # Image 205: corrupted file
        corrupted_path = cls.test_upload_dir / "event_101_corrupted_205.jpg"
        with open(corrupted_path, "wb") as f:
            f.write(b"NOT_A_VALID_IMAGE_DATA_12345")

        cur.executemany("""
            INSERT OR REPLACE INTO images (id, event_id, image_path, processing_status)
            VALUES (?, ?, ?, ?);
        """, [
            (201, 101, "uploads/event_images/event_101_img_201.jpg", "pending"),
            (202, 102, "uploads/event_images/event_102_img_202.jpg", "pending"),
            (203, 103, "uploads/event_images/event_103_img_203.jpg", "pending"),
            (204, 101, "uploads/event_images/event_101_missing_204.jpg", "pending"),
            (205, 101, "uploads/event_images/event_101_corrupted_205.jpg", "pending"),
            (206, 102, "uploads/event_images/event_102_img_206.jpg", "pending"),
            (207, 101, "uploads/event_images/event_101_solid_207.jpg", "pending"),
            (208, 101, "uploads/event_images/event_101_overwrite_208.jpg", "completed"),
        ])

        # Seed existing analysis for Image 208
        cur.execute("""
            INSERT OR REPLACE INTO crowd_analyses (id, image_id, predicted_count, processing_status, model_name)
            VALUES (88, 208, 120, 'completed', 'CSRNet');
        """)
        cls.sqlite_conn.commit()


    def setUp(self):
        self.client = self.app.test_client()

    def login_as(self, email, password):
        """Helper to authenticate user session."""
        return self.client.post('/api/auth/login', json={
            'email': email,
            'password': password
        })

    def mock_prediction(self, count=42):
        """Mock return value for CrowdPredictor.predict."""
        return {
            "predicted_count": count,
            "raw_density_sum": float(count) + 0.15,
            "density_stats": {
                "min": -0.0001,
                "max": 0.85,
                "mean": 0.0035,
                "std": 0.045,
                "sum": float(count) + 0.15,
                "negative_pixels": 150,
                "positive_pixels": 2250,
                "zero_pixels": 0,
                "total_pixels": 2400,
                "negative_pixel_pct": 6.25
            },
            "original_resolution": [160, 120],
            "density_map_shape": [15, 20],
            "device": "cpu",
            "inference_time_ms": 12.5,
            "model_name": "CSRNet",
            "weights_file": "shanghaitech_part_b.pth"
        }

    # -------------------------------------------------------------------------
    # TESTS
    # -------------------------------------------------------------------------
    def test_01_organizer_can_analyze_own_approved_event_image(self):
        """TEST 1: Authenticated organizer can analyze their own approved event image (HTTP 200)."""
        self.login_as("org1@test.edu", "Org1@123")

        with patch("ai.predictor.CrowdPredictor.predict", return_value=self.mock_prediction(count=85)):
            resp = self.client.post('/api/images/201/analyze')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("analysis", data)
        analysis = data["analysis"]
        self.assertEqual(analysis["image_id"], 201)
        self.assertEqual(analysis["event_id"], 101)
        self.assertEqual(analysis["predicted_count"], 85)
        self.assertEqual(analysis["processing_status"], "completed")
        self.assertEqual(analysis["model_name"], "CSRNet")
        self.assertIn("density_stats", analysis)

        # Verify image processing_status updated in database
        img = ImageModel.get_by_id(201)
        self.assertEqual(img["processing_status"], "completed")

        # Verify record in crowd_analyses
        ca = CrowdAnalysisModel.get_by_image_id(201)
        self.assertIsNotNone(ca)
        self.assertEqual(ca["predicted_count"], 85)

    def test_02_admin_can_analyze_any_event_image(self):
        """TEST 2: Authenticated administrator can analyze any event image (HTTP 200)."""
        self.login_as("admin@test.edu", "Admin@123")

        with patch("ai.predictor.CrowdPredictor.predict", return_value=self.mock_prediction(count=120)):
            resp = self.client.post('/api/events/102/images/202/analyze')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["analysis"]["predicted_count"], 120)

    def test_03_unauthenticated_request_rejected(self):
        """TEST 3: Unauthenticated request is rejected (HTTP 401)."""
        resp = self.client.post('/api/images/201/analyze')
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["error"], "Unauthorized")

    def test_04_organizer_cannot_analyze_another_organizers_image(self):
        """TEST 4: Organizer cannot analyze another organizer's event image (HTTP 403)."""
        # Organizer 1 tries to analyze Image 202 (belongs to Organizer 2's Event 102)
        self.login_as("org1@test.edu", "Org1@123")

        resp = self.client.post('/api/images/202/analyze')
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data["error"], "Forbidden")

    def test_05_nonexistent_image_returns_404(self):
        """TEST 5: Non-existent image returns HTTP 404 Not Found."""
        self.login_as("org1@test.edu", "Org1@123")

        resp = self.client.post('/api/images/9999/analyze')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data["error"], "Not Found")

    def test_06_mismatched_event_id_returns_400(self):
        """TEST 6: Mismatched event ID returns HTTP 400 Bad Request."""
        self.login_as("org1@test.edu", "Org1@123")

        # Image 201 belongs to Event 101, not Event 102
        resp = self.client.post('/api/events/102/images/201/analyze')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["error"], "Bad Request")

    def test_07_image_for_unapproved_event_returns_400(self):
        """TEST 7: Image for pending/rejected event returns HTTP 400 Bad Request."""
        self.login_as("org1@test.edu", "Org1@123")

        # Image 203 belongs to Event 103 (status: 'pending')
        resp = self.client.post('/api/images/203/analyze')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["error"], "Bad Request")
        self.assertIn("approved", data["message"].lower())

    def test_08_missing_file_on_storage_returns_404_and_marks_failed(self):
        """TEST 8: Missing image file on storage returns HTTP 404 and marks image as failed."""
        self.login_as("org1@test.edu", "Org1@123")

        # Image 204 does not exist on disk
        resp = self.client.post('/api/images/204/analyze')
        self.assertEqual(resp.status_code, 404)

        img = ImageModel.get_by_id(204)
        self.assertEqual(img["processing_status"], "failed")

    def test_09_corrupted_file_returns_422_and_marks_failed(self):
        """TEST 9: Corrupted image file on storage returns HTTP 422 and marks image as failed."""
        self.login_as("org1@test.edu", "Org1@123")

        # Image 205 has corrupted non-image bytes
        resp = self.client.post('/api/images/205/analyze')
        self.assertEqual(resp.status_code, 422)

        img = ImageModel.get_by_id(205)
        self.assertEqual(img["processing_status"], "failed")

    def test_10_repeated_analysis_updates_existing_record_safely(self):
        """TEST 10: Repeated/duplicate analysis request safely updates existing record (upsert)."""
        self.login_as("org1@test.edu", "Org1@123")

        # First analysis with count=50
        with patch("ai.predictor.CrowdPredictor.predict", return_value=self.mock_prediction(count=50)):
            resp1 = self.client.post('/api/images/201/analyze')
        self.assertEqual(resp1.status_code, 200)
        ca1 = CrowdAnalysisModel.get_by_image_id(201)
        self.assertEqual(ca1["predicted_count"], 50)
        analysis_id = ca1["id"]

        # Second analysis with updated count=95 (e.g. re-run)
        with patch("ai.predictor.CrowdPredictor.predict", return_value=self.mock_prediction(count=95)):
            resp2 = self.client.post('/api/images/201/analyze')
        self.assertEqual(resp2.status_code, 200)
        ca2 = CrowdAnalysisModel.get_by_image_id(201)
        self.assertEqual(ca2["id"], analysis_id)  # Same ID, not a duplicate record
        self.assertEqual(ca2["predicted_count"], 95)

    def test_11_get_image_analysis_returns_persisted_record(self):
        """TEST 11: GET /api/images/<image_id>/analysis returns analysis record (HTTP 200)."""
        self.login_as("org1@test.edu", "Org1@123")

        resp = self.client.get('/api/images/201/analysis')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["analysis"]["image_id"], 201)
        self.assertEqual(data["analysis"]["predicted_count"], 95)

    def test_12_get_image_analysis_enforces_authorization(self):
        """TEST 12: GET /api/images/<image_id>/analysis enforces role authorization (HTTP 403)."""
        # Organizer 2 attempts to view Organizer 1's analysis
        self.login_as("org2@test.edu", "Org2@123")

        resp = self.client.get('/api/images/201/analysis')
        self.assertEqual(resp.status_code, 403)

    def test_13_get_image_analysis_returns_404_when_unopened(self):
        """TEST 13: GET /api/images/<image_id>/analysis returns 404 when not analyzed."""
        self.login_as("org2@test.edu", "Org2@123")

        # Image 206 has not been analyzed yet
        resp = self.client.get('/api/images/206/analysis')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertIn("No crowd analysis found", data["message"])


    def test_14_inference_failure_returns_safe_500(self):
        """TEST 14: Model inference failure returns safe HTTP 500 without leaking stack traces."""
        self.login_as("org1@test.edu", "Org1@123")

        with patch("ai.predictor.CrowdPredictor.predict", side_effect=RuntimeError("CUDA out of memory in test")):
            resp = self.client.post('/api/images/201/analyze')

        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data["error"], "Internal Server Error")
        # Ensure raw internal error / paths are not leaked
        self.assertNotIn("CUDA", data["message"])
        self.assertNotIn("test_stage7_analysis", data["message"])
        self.assertNotIn("Traceback", data["message"])

    def test_15_real_end_to_end_inference_execution(self):
        """TEST 15: Real end-to-end inference executes and persists correctly."""
        weights_file = BACKEND_DIR / "ai" / "weights" / "shanghaitech_part_b.pth"
        if not weights_file.is_file():
            self.skipTest("Pretrained weights not available on disk.")

        self.login_as("org1@test.edu", "Org1@123")

        # Run without mock on real image file
        resp = self.client.post('/api/images/201/analyze')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["analysis"]["predicted_count"], int)
        self.assertGreaterEqual(data["analysis"]["predicted_count"], 0)
        self.assertEqual(data["analysis"]["model_name"], "CSRNet")

    def test_16_completely_solid_image_is_rejected_before_inference(self):
        """TEST 16: Completely uniform solid-colour image is rejected before inference (HTTP 422)."""
        self.login_as("org1@test.edu", "Org1@123")

        # Mock predict with an exception to guarantee inference is NOT called
        with patch("ai.predictor.CrowdPredictor.predict", side_effect=AssertionError("Predict should not be called")):
            resp = self.client.post('/api/images/207/analyze')

        self.assertEqual(resp.status_code, 422)
        data = resp.get_json()
        self.assertEqual(data["error"], "Unprocessable Entity")
        self.assertIn("blank or completely uniform", data["message"].lower())
        # Does not expose internal paths
        self.assertNotIn("event_101_solid_207", data["message"])
        self.assertNotIn("test_stage7_analysis", data["message"])

        # Verify no crowd analysis record was saved in database
        analysis = CrowdAnalysisModel.get_by_image_id(207)
        self.assertIsNone(analysis)

        # Verify image processing status was marked as failed
        img = ImageModel.get_by_id(207)
        self.assertEqual(img["processing_status"], "failed")

    def test_17_rejected_blank_image_does_not_overwrite_previous_analysis(self):
        """TEST 17: Rejected blank-image validation does not overwrite a previously successful analysis."""
        self.login_as("org1@test.edu", "Org1@123")

        # Image 208 was seeded with an existing completed analysis (count=120)
        with patch("ai.predictor.CrowdPredictor.predict", side_effect=AssertionError("Predict should not be called")):
            resp = self.client.post('/api/images/208/analyze')

        self.assertEqual(resp.status_code, 422)
        data = resp.get_json()
        self.assertEqual(data["error"], "Unprocessable Entity")
        self.assertIn("blank or completely uniform", data["message"].lower())

        # Verify previous analysis was preserved intact
        analysis = CrowdAnalysisModel.get_by_image_id(208)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis["predicted_count"], 120)
        self.assertEqual(analysis["processing_status"], "completed")

        # Verify image processing_status remained completed (not overwritten to failed)
        img = ImageModel.get_by_id(208)
        self.assertEqual(img["processing_status"], "completed")

    def test_18_existing_empty_baseline_fixture_is_detected_as_uniform(self):
        """TEST 18: Existing empty baseline fixture and synthetic solid images are correctly detected."""
        empty_fixture = BACKEND_DIR / "tests" / "fixtures" / "empty_baseline.jpg"
        if empty_fixture.is_file():
            self.assertTrue(is_blank_or_uniform_image(empty_fixture))

        # Synthetic solid images (black, white, blue)
        solid_black = Image.new('RGB', (100, 100), (0, 0, 0))
        self.assertTrue(is_blank_or_uniform_image(solid_black))

        solid_white = Image.new('RGB', (100, 100), (255, 255, 255))
        self.assertTrue(is_blank_or_uniform_image(solid_white))

        solid_blue = Image.new('RGB', (640, 480), (41, 60, 100))
        self.assertTrue(is_blank_or_uniform_image(solid_blue))

    def test_19_auditorium_photo_passes_blank_validation(self):
        """TEST 19: Genuine photographs with rich visual features pass blank validation."""
        auditorium_photo = BACKEND_DIR / "uploads" / "event_images" / "event_9034_20261019_121905_29b4df5f.jpg"
        if auditorium_photo.is_file():
            self.assertFalse(is_blank_or_uniform_image(auditorium_photo))

        crowd_fixture = BACKEND_DIR / "tests" / "fixtures" / "6.jpg"
        if crowd_fixture.is_file():
            self.assertFalse(is_blank_or_uniform_image(crowd_fixture))

        # Synthetic non-uniform image with large plain background and small subject
        bg_img = Image.new('RGB', (200, 200), (240, 240, 240))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(bg_img)
        draw.rectangle([50, 50, 80, 80], fill=(20, 20, 20))
        self.assertFalse(is_blank_or_uniform_image(bg_img))

    def test_20_unreadable_or_corrupt_image_handled_safely(self):
        """TEST 20: Corrupted or unreadable image file is handled safely without inference."""
        self.login_as("org1@test.edu", "Org1@123")

        with patch("ai.predictor.CrowdPredictor.predict", side_effect=AssertionError("Predict should not be called")):
            resp = self.client.post('/api/images/205/analyze')

        self.assertEqual(resp.status_code, 422)
        data = resp.get_json()
        self.assertEqual(data["error"], "Unprocessable Entity")
        self.assertIn("invalid or corrupted", data["message"].lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)

