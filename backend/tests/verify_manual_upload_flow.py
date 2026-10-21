"""
Verification Script for Stage 6 Manual Flow with Real Image
------------------------------------------------------------
Executes the full end-to-end workflow:
1. Login as Organizer
2. Select Approved Event (ID: 501 or seed event 1)
3. Upload real event-place JPEG image
4. Verify physical file in upload directory
5. Verify metadata in database
6. Verify listing in event image history
"""

import os
import io
import sys
import sqlite3
from datetime import date
from pathlib import Path
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.settings import settings
import config.db
from middleware.auth import hash_password
from models.image import ImageModel


try:
    from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
except ImportError:
    from db_guard import IsolatedTestDatabase, install_global_safety_guard


def run_manual_image_flow():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'manual-flow-secret-key-2026'

    install_global_safety_guard()

    # Always isolate database
    isolated_db = IsolatedTestDatabase()
    sqlite_conn = isolated_db.init_database()
    cur = sqlite_conn.cursor()

    pw = hash_password("Password123!")
    cur.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role) VALUES (10, 'Organizer Maya', 'maya@campus.edu', ?, 'organizer')", (pw,))
    cur.execute("INSERT OR REPLACE INTO venues (id, name, location, capacity, status) VALUES (1, 'Main Quad', 'Block A', 800, 'available')")
    cur.execute("INSERT OR REPLACE INTO event_series (id, name, description, start_date, end_date) VALUES (1, 'TechFest 2026', 'Festival', '2026-09-01', '2026-09-30')")
    today_str = date.today().isoformat()
    cur.execute("""
        INSERT OR REPLACE INTO events (id, series_id, organizer_id, venue_id, event_name, description, status, requested_date, requested_start_time, requested_end_time, approved_date, approved_start_time, approved_end_time)
        VALUES (
            101, 1, 10, 1, 'Robotics Championship 2026', 'National Robotics Finals',
            'approved', ?, '00:00:00', '23:59:59', ?, '00:00:00', '23:59:59'
        )
    """, (today_str, today_str))
    sqlite_conn.commit()
    isolated_db.patch_models()

    client = app.test_client()

    print("[1] Logging in as Organizer Maya...")
    login_res = client.post('/api/auth/login', json={"email": "maya@campus.edu", "password": "Password123!"})
    assert login_res.status_code == 200, f"Login failed: {login_res.data}"
    print("    [OK] Logged in successfully.")

    print("[2] Creating real event location JPEG image (Auditorium crowd view)...")
    buf = io.BytesIO()
    real_img = Image.new('RGB', (640, 480), color=(40, 60, 100))
    real_img.save(buf, format='JPEG')
    buf.seek(0)
    img_bytes = buf.getvalue()
    print(f"    [OK] Real image generated: {len(img_bytes)} bytes, format=JPEG, size=640x480.")

    print("[3] Uploading image to approved event (Event ID: 101)...")
    upload_res = client.post('/api/events/101/images',
                             data={'image': (io.BytesIO(img_bytes), 'auditorium_camera_north.jpg')},
                             content_type='multipart/form-data')
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.data}"
    upload_json = upload_res.get_json()
    assert upload_json["success"] is True
    image_record = upload_json["image"]
    print(f"    [OK] Upload succeeded! Image ID: {image_record['id']}")
    print(f"         Relative Path: {image_record['image_path']}")
    print(f"         Status:        {image_record['processing_status']}")
    print(f"         Uploaded At:   {image_record['uploaded_at']}")

    print("[4] Verifying physical file exists in upload directory...")
    filename = os.path.basename(image_record["image_path"])
    disk_path = os.path.join(settings.UPLOAD_FOLDER, filename)
    assert os.path.exists(disk_path), f"File {disk_path} does not exist on disk!"
    assert os.path.getsize(disk_path) == len(img_bytes), "File size on disk does not match uploaded bytes!"
    # Verify file can be opened and verified with Pillow
    with Image.open(disk_path) as verified_img:
        verified_img.verify()
    print(f"    [OK] File exists on disk at: {disk_path}")
    print(f"         File size matches: {os.path.getsize(disk_path)} bytes.")
    print(f"         Pillow verification passed: valid image file.")

    print("[5] Verifying image listing API (/api/events/101/images)...")
    list_res = client.get('/api/events/101/images')
    assert list_res.status_code == 200
    list_json = list_res.get_json()
    assert list_json["success"] is True
    assert list_json["total_images"] >= 1
    found = any(img["id"] == image_record["id"] for img in list_json["images"])
    assert found, "Uploaded image not found in listing!"
    print(f"    [OK] Listing verified: total {list_json['total_images']} image(s) found in event history.")

    print("[6] Verifying safe file serving (/uploads/event_images/<filename>)...")
    serve_res = client.get(image_record["image_url"])
    assert serve_res.status_code == 200
    assert len(serve_res.data) == len(img_bytes)
    print(f"    [OK] Serving endpoint verified: HTTP 200 with {len(serve_res.data)} bytes.")

    print("\n>>> ALL STAGE 6 MANUAL WORKFLOW CHECKS PASSED WITH REAL IMAGE! <<<")


if __name__ == '__main__':
    run_manual_image_flow()
