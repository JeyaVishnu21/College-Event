"""
Verify Step 4B Dashboard Visual Refinements
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import json
from config.db import get_db_connection
from werkzeug.security import generate_password_hash
from app import create_app

def run_tests():
    app = create_app()
    client = app.test_client()

    print("==================================================")
    print("STEP 4B DASHBOARD VISUAL REFINEMENT VERIFICATION")
    print("==================================================")

    # 1. Update test password hashes
    conn = get_db_connection()
    try:
        with conn.cursor() as c:
            pwd_hash = generate_password_hash("Password123!")
            c.execute(
                "UPDATE users SET password_hash = %s WHERE email IN ('student_test_1791211266@college.edu', 'organizer_test_1791211266@college.edu', 'mgmt_admin_1791211266@college.edu', 'vishnu@gmail.com')",
                (pwd_hash,)
            )
            conn.commit()
    finally:
        conn.close()

    # TEST 1: STUDENT
    print("\n--- 1. TESTING STUDENT DASHBOARD APIs ---")
    res = client.post('/api/auth/login', json={'email': 'student_test_1791211266@college.edu', 'password': 'Password123!'})
    assert res.status_code == 200, f"Student login failed: {res.data}"
    user = res.get_json()['user']
    print(f"  [PASS] Student Authenticated: {user['email']} (role: {user['role']})")

    ev_res = client.get('/api/public/events')
    assert ev_res.status_code == 200
    evs = ev_res.get_json()['events']
    print(f"  [PASS] Public approved events: {len(evs)}")
    assert len(evs) > 0

    det_res = client.get(f'/api/public/events/{evs[0]["id"]}')
    assert det_res.status_code == 200
    det = det_res.get_json()['event']
    print(f"  [PASS] Event Detail with crowd_info: {det['event_name']}, crowd_info: {det['crowd_info']}")

    v_res = client.get('/api/venues')
    assert v_res.status_code == 200
    venues = v_res.get_json()['venues']
    print(f"  [PASS] Venues count: {len(venues)}")

    client.post('/api/auth/logout')

    # TEST 2: ORGANIZER
    print("\n--- 2. TESTING ORGANIZER DASHBOARD APIs ---")
    res = client.post('/api/auth/login', json={'email': 'vishnu@gmail.com', 'password': 'Password123!'})
    assert res.status_code == 200, f"Organizer login failed: {res.data}"
    org = res.get_json()['user']
    print(f"  [PASS] Organizer Authenticated: {org['email']} (role: {org['role']})")

    dash_res = client.get('/api/organizer/dashboard')
    assert dash_res.status_code == 200
    dash_data = dash_res.get_json()
    stats = dash_data['stats']
    print(f"  [PASS] Organizer Stats: {stats}")
    print(f"  [PASS] Organizer Events: {len(dash_data['events'])} items")
    print(f"  [PASS] Organizer Upcoming: {len(dash_data['upcoming_events'])} items")
    assert stats['total_events'] == len(dash_data['events'])

    client.post('/api/auth/logout')

    # TEST 3: MANAGEMENT
    print("\n--- 3. TESTING MANAGEMENT DASHBOARD APIs ---")
    res = client.post('/api/auth/login', json={'email': 'mgmt_admin_1791211266@college.edu', 'password': 'Password123!'})
    assert res.status_code == 200, f"Management login failed: {res.data}"
    mgmt = res.get_json()['user']
    print(f"  [PASS] Management Authenticated: {mgmt['email']} (role: {mgmt['role']})")

    m_dash_res = client.get('/api/management/dashboard')
    assert m_dash_res.status_code == 200
    m_data = m_dash_res.get_json()
    print(f"  [PASS] Management Stats: {m_data['stats']}")
    print(f"  [PASS] Pending requests: {len(m_data['pending_requests'])}")
    print(f"  [PASS] Upcoming events: {len(m_data['upcoming_events'])}")
    print(f"  [PASS] Venues: {len(m_data['venues'])}")

    client.post('/api/auth/logout')

    # TEST 4: FRESH ORGANIZER EMPTY STATE
    print("\n--- 4. TESTING FRESH ORGANIZER EMPTY STATE ---")
    res = client.post('/api/auth/login', json={'email': 'organizer_test_1791211266@college.edu', 'password': 'Password123!'})
    assert res.status_code == 200
    fresh_data = client.get('/api/organizer/dashboard').get_json()
    print(f"  [PASS] Fresh Organizer: stats={fresh_data['stats']}, events={len(fresh_data['events'])}, upcoming={len(fresh_data['upcoming_events'])}")
    assert fresh_data['stats']['total_events'] == 0
    assert len(fresh_data['events']) == 0
    assert len(fresh_data['upcoming_events']) == 0

    client.post('/api/auth/logout')

    print("\n==================================================")
    print("ALL STEP 4B TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == '__main__':
    run_tests()
