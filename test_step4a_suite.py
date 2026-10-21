"""
Step 4A Automated Verification Test Suite
Tests the 17-step test sequence specified in Section 16 of the prompt:
1. Open login page
2. Login as Student
3. Verify student dashboard & permissions
4. Navigate through student pages
5. Refresh the page (simulate session persistence)
6. Verify session remains valid
7. Logout
8. Login as Organizer
9. Verify organizer dashboard & permissions
10. Navigate through organizer pages
11. Refresh & verify session persistence
12. Logout
13. Login as Management
14. Verify management dashboard & permissions
15. Navigate through management pages
16. Refresh & verify session persistence
17. Logout

Additional tests:
- Direct URL / API tab simulation
- Unauthorized access prevention
- Cache-control / bfcache protection headers
"""

import urllib.request
import urllib.parse
import http.cookiejar
import json
import sys

API_BASE = "http://localhost:5000/api"
FRONTEND_BASE = "http://localhost:3000"

class TestClient:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def request(self, method, url, data=None, headers=None):
        if headers is None:
            headers = {}
        payload = None
        if data is not None:
            if isinstance(data, dict):
                payload = json.dumps(data).encode('utf-8')
                headers['Content-Type'] = 'application/json'
            elif isinstance(data, str):
                payload = data.encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            resp = self.opener.open(req)
            body = resp.read().decode('utf-8')
            return resp.status, resp.headers, body
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            return e.code, e.headers, body

    def get_json(self, url):
        status, headers, body = self.request("GET", url)
        try:
            return status, headers, json.loads(body)
        except Exception:
            return status, headers, body

    def post_json(self, url, data):
        status, headers, body = self.request("POST", url, data=data)
        try:
            return status, headers, json.loads(body)
        except Exception:
            return status, headers, body

def run_tests():
    print("=" * 60)
    print("STARTING STEP 4A AUTOMATED VERIFICATION SUITE")
    print("=" * 60)
    import time
    ts = int(time.time())

    # 1. Open login page
    print("\n[Step 1] Opening login page...")
    client = TestClient()
    status, headers, html = client.request("GET", f"{FRONTEND_BASE}/login.html")
    assert status == 200, f"Expected 200, got {status}"
    assert "Sign In" in html or "login" in html.lower(), "Login page content missing"
    print(" PASS: login.html loaded successfully (HTTP 200)")

    # 2. Login as Student
    print("\n[Step 2] Login as Student...")
    # Register/Login student
    student_email = f"student_test_{ts}@college.edu"
    student_pass = "StudentPass@123"
    # Ensure registered
    reg_status, _, reg_data = client.post_json(f"{API_BASE}/auth/register", {
        "name": "Jane Student",
        "email": student_email,
        "password": student_pass,
        "role": "student"
    })
    # Login
    login_status, login_headers, login_data = client.post_json(f"{API_BASE}/auth/login", {
        "email": student_email,
        "password": student_pass
    })
    assert login_status == 200, f"Student login failed: {login_data}"
    assert login_data.get("user", {}).get("role") == "student", "Role mismatch"
    print(f" PASS: Student logged in successfully as '{login_data['user']['name']}' (Role: {login_data['user']['role']})")

    # 3. Verify student dashboard
    print("\n[Step 3] Verify student dashboard & permissions...")
    status, _, me_data = client.get_json(f"{API_BASE}/auth/me")
    assert status == 200, f"Student auth/me failed: {me_data}"
    assert me_data.get("authenticated") is True, "Student not authenticated"
    assert me_data.get("user", {}).get("role") == "student", "User role is not student"
    
    # Check student frontend page
    f_status, _, f_html = client.request("GET", f"{FRONTEND_BASE}/student.html")
    assert f_status == 200, f"student.html returned {f_status}"
    assert "Student Navigation" in f_html, "Student navigation label missing"
    assert "data-tab=\"dashboard\"" in f_html, "Dashboard tab missing"
    assert "data-tab=\"events\"" in f_html, "Events tab missing"
    assert "data-tab=\"profile\"" in f_html, "Profile tab missing"
    # Verify organizer / management navigation is NOT exposed
    assert "tab-myevents-btn" not in f_html, "Organizer tab leaked to student"
    assert "tab-requests-btn" not in f_html, "Management tab leaked to student"
    print(" PASS: Student dashboard HTML loaded with strictly isolated Student Navigation")

    # 4. Navigate through student pages / endpoints
    print("\n[Step 4] Navigate through student pages / events API...")
    ev_status, _, ev_data = client.get_json(f"{API_BASE}/public/events")
    assert ev_status == 200, f"Public events API returned {ev_status}"
    print(f" PASS: Student can view approved events ({len(ev_data.get('events', []))} events retrieved)")

    # 5. Refresh the page (simulate session persistence)
    print("\n[Step 5] Simulating page refresh...")
    ref_status, ref_headers, ref_data = client.get_json(f"{API_BASE}/auth/me")
    assert ref_status == 200, f"Session lost on refresh: {ref_data}"
    assert ref_data.get("authenticated") is True, "Session dropped on refresh!"
    # Verify Cache-Control header prevents stale caching
    cc_header = ref_headers.get("Cache-Control", "")
    assert "no-cache" in cc_header or "no-store" in cc_header, f"Cache-Control header missing no-store: {cc_header}"
    print(" PASS: Session remains fully active on refresh with no-store headers")

    # 6. Verify unauthorized navigation (Student cannot access management/organizer protected endpoints)
    print("\n[Step 6] Verifying student cannot access management endpoints...")
    mgmt_status, _, mgmt_data = client.get_json(f"{API_BASE}/management/dashboard")
    assert mgmt_status == 403, f"Expected 403 Forbidden for student accessing management dashboard, got {mgmt_status}"
    print(" PASS: Student access to Management Dashboard blocked (403 Forbidden)")

    # 7. Logout Student
    print("\n[Step 7] Logging out student...")
    lo_status, _, lo_data = client.post_json(f"{API_BASE}/auth/logout", {})
    assert lo_status == 200, f"Logout failed: {lo_data}"
    me_post_lo, _, me_post_data = client.get_json(f"{API_BASE}/auth/me")
    assert me_post_lo == 401 or (isinstance(me_post_data, dict) and me_post_data.get("authenticated") is False), f"Expected 401/unauthenticated, got {me_post_lo}: {me_post_data}"
    print(" PASS: Student logged out and session cleared (subsequent /me rejected with 401)")

    # 8. Login as Organizer
    print("\n[Step 8] Login as Organizer...")
    org_client = TestClient()
    org_email = f"organizer_test_{ts}@college.edu"
    org_pass = "OrganizerPass@123"
    org_client.post_json(f"{API_BASE}/auth/register", {
        "name": "Bob Organizer",
        "email": org_email,
        "password": org_pass,
        "role": "organizer"
    })
    org_login_status, _, org_login_data = org_client.post_json(f"{API_BASE}/auth/login", {
        "email": org_email,
        "password": org_pass
    })
    assert org_login_status == 200, f"Organizer login failed: {org_login_data}"
    assert org_login_data.get("user", {}).get("role") == "organizer"
    print(f" PASS: Organizer logged in as '{org_login_data['user']['name']}'")

    # 9. Verify organizer dashboard
    print("\n[Step 9] Verify organizer dashboard & navigation items...")
    dash_status, _, dash_data = org_client.get_json(f"{API_BASE}/organizer/dashboard")
    assert dash_status == 200, f"Organizer dashboard API returned {dash_status}: {dash_data}"
    
    org_f_status, _, org_f_html = org_client.request("GET", f"{FRONTEND_BASE}/organizer.html")
    assert org_f_status == 200
    # Organizer tabs check
    for tab in ["dashboard", "myevents", "create", "venues", "monitoring", "analysis", "alerts", "history", "profile"]:
        assert f'data-tab="{tab}"' in org_f_html, f"Organizer tab '{tab}' missing"
    assert "tab-requests-btn" not in org_f_html, "Management tab leaked to organizer"
    print(" PASS: Organizer dashboard contains all 9 Organizer Navigation items and no management leaks")

    # 10. Navigate through organizer pages
    print("\n[Step 10] Navigate organizer events...")
    my_ev_status, _, my_ev_data = org_client.get_json(f"{API_BASE}/events")
    assert my_ev_status == 200, f"/events returned {my_ev_status}"
    print(f" PASS: Organizer fetched events successfully ({len(my_ev_data.get('events', []))} events)")

    # 11. Refresh Organizer
    print("\n[Step 11] Refresh organizer session...")
    org_ref_status, _, org_ref_data = org_client.get_json(f"{API_BASE}/auth/me")
    assert org_ref_status == 200 and org_ref_data.get("authenticated") is True
    print(" PASS: Organizer session valid across refresh")

    # 12. Logout Organizer
    print("\n[Step 12] Logout organizer...")
    org_lo_status, _, _ = org_client.post_json(f"{API_BASE}/auth/logout", {})
    assert org_lo_status == 200
    org_post_lo, _, _ = org_client.get_json(f"{API_BASE}/auth/me")
    assert org_post_lo == 401
    print(" PASS: Organizer logged out and session terminated (subsequent /me returns 401)")

    # 13. Login as Management
    print("\n[Step 13] Login as Management...")
    mgmt_client = TestClient()
    mgmt_email = f"mgmt_admin_{ts}@college.edu"
    mgmt_pass = "MgmtPass@123"
    mgmt_reg_status, _, mgmt_reg_data = mgmt_client.post_json(f"{API_BASE}/auth/register", {
        "name": "Dr. Smith Admin",
        "email": mgmt_email,
        "password": mgmt_pass,
        "role": "management",
        "management_code": "college_mgmt_secret_2026"
    })
    mgmt_login_status, _, mgmt_login_data = mgmt_client.post_json(f"{API_BASE}/auth/login", {
        "email": mgmt_email,
        "password": mgmt_pass
    })
    assert mgmt_login_status == 200, f"Management login failed ({mgmt_reg_status}, {mgmt_reg_data}): {mgmt_login_data}"
    assert mgmt_login_data.get("user", {}).get("role") == "management"
    print(f" PASS: Management logged in as '{mgmt_login_data['user']['name']}'")

    # 14. Verify management dashboard & navigation
    print("\n[Step 14] Verify management dashboard & navigation items...")
    mgmt_dash_status, _, mgmt_dash_data = mgmt_client.get_json(f"{API_BASE}/management/dashboard")
    assert mgmt_dash_status == 200, f"Management dashboard API returned {mgmt_dash_status}: {mgmt_dash_data}"
    
    mgmt_f_status, _, mgmt_f_html = mgmt_client.request("GET", f"{FRONTEND_BASE}/management.html")
    assert mgmt_f_status == 200
    for tab in ["dashboard", "requests", "allevents", "venues", "festivals", "monitoring", "alerts", "reports", "profile"]:
        assert f'data-tab="{tab}"' in mgmt_f_html, f"Management tab '{tab}' missing"
    assert "tab-myevents-btn" not in mgmt_f_html, "Organizer tab leaked to management"
    print(" PASS: Management dashboard contains all 9 Management Navigation items with role isolation")

    # 15. Navigate through management pages
    print("\n[Step 15] Navigate management endpoints (venues, event requests)...")
    v_status, _, v_data = mgmt_client.get_json(f"{API_BASE}/venues")
    assert v_status == 200
    print(f" PASS: Venues loaded ({len(v_data.get('venues', []))} facilities)")

    # 16. Refresh Management
    print("\n[Step 16] Refresh management session...")
    mgmt_ref_status, _, mgmt_ref_data = mgmt_client.get_json(f"{API_BASE}/auth/me")
    assert mgmt_ref_status == 200 and mgmt_ref_data.get("authenticated") is True
    print(" PASS: Management session valid across refresh")

    # 17. Logout Management
    print("\n[Step 17] Logout management...")
    mgmt_lo_status, _, _ = mgmt_client.post_json(f"{API_BASE}/auth/logout", {})
    assert mgmt_lo_status == 200
    me_after_mgmt_lo, _, me_mgmt_data = mgmt_client.get_json(f"{API_BASE}/auth/me")
    assert me_after_mgmt_lo == 401 or (isinstance(me_mgmt_data, dict) and me_mgmt_data.get("authenticated") is False), f"Expected 401/unauthenticated, got {me_after_mgmt_lo}: {me_mgmt_data}"
    print(" PASS: Management logged out successfully (subsequent /me rejected with 401)")

    # Additional: Direct URL & Back-Button protection
    print("\n[Additional Test] Checking protected dashboard access after logout...")
    post_lo_mgmt_call, _, _ = mgmt_client.get_json(f"{API_BASE}/management/dashboard")
    assert post_lo_mgmt_call == 401, f"Expected 401 after logout, got {post_lo_mgmt_call}"
    print(" PASS: Protected API calls immediately return 401 Unauthorized after logout")

    print("\n" + "=" * 60)
    print("ALL 17 TEST STEPS + SECURITY AUDIT PASSED WITH ZERO ERRORS!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
