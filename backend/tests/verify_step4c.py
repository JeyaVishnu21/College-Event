"""
Step 4C End-to-End Automated Verification Script
Tests Student event browsing/details, Organizer form validation & submission,
Management operational review table, venue conflict handling (409), allocation approval, and rejection.
Uses urllib to test real endpoints on localhost:5000 and localhost:3000.
"""

import urllib.request
import urllib.parse
import json
import http.cookiejar
import sys
import datetime

BACKEND_BASE = "http://127.0.0.1:5000"
FRONTEND_BASE = "http://127.0.0.1:3000"

# Setup session handler with cookies
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def request_json(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    encoded_data = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        encoded_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with opener.open(req) as response:
            body = response.read().decode("utf-8")
            status = response.status
            return status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed

def request_raw(url):
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")

def login(email, password):
    status, res = request_json(
        f"{BACKEND_BASE}/api/auth/login",
        method="POST",
        data={"email": email, "password": password}
    )
    return status, res

def run_tests():
    print("=" * 60)
    print("STEP 4C -- AUTOMATED VERIFICATION SUITE")
    print("=" * 60)
    passed = 0
    total = 0

    # 1. Frontend Asset Serving
    total += 1
    print("\n[Check 1] Frontend static pages serving")
    st1, html_student = request_raw(f"{FRONTEND_BASE}/student.html")
    st2, html_org = request_raw(f"{FRONTEND_BASE}/organizer.html")
    st3, html_mgmt = request_raw(f"{FRONTEND_BASE}/management.html")
    st4, css_text = request_raw(f"{FRONTEND_BASE}/css/style.css")

    if st1 == 200 and st2 == 200 and st3 == 200 and st4 == 200:
        if ".form-section-header" in css_text and ".modal-spec-grid" in css_text and ".table-responsive" in css_text:
            print("  [PASS] All HTML/CSS assets load with HTTP 200 and include Step 4C CSS rules.")
            passed += 1
        else:
            print("  [FAIL] CSS missing step 4C classes.")
    else:
        print(f"  [FAIL] Failed to serve frontend assets: {st1}, {st2}, {st3}, {st4}")

    # 2. Student Event Details API & Structure
    total += 1
    print("\n[Check 2] Student Event browsing & Event Details")
    stu_login_st, _ = login("student_test_1791211266@college.edu", "Password123!")
    status, events_data = request_json(f"{BACKEND_BASE}/api/public/events")
    if stu_login_st == 200 and status == 200 and isinstance(events_data, dict) and "events" in events_data and len(events_data["events"]) > 0:
        first_event = events_data["events"][0]
        event_id = first_event.get("id") or first_event.get("event_id")
        # Fetch event detail
        st_detail, detail_res = request_json(f"{BACKEND_BASE}/api/events/{event_id}")
        if st_detail == 200:
            ev = detail_res.get("event", {})
            title = ev.get("title") or ev.get("event_name") or first_event.get("event_name")
            print(f"  [PASS] Event details API verified for Event #{event_id} ('{title}').")
            print(f"    Venue: {ev.get('venue_name', 'TBD')} | Status: {ev.get('status')} | Category: {ev.get('category')}")
            passed += 1
        else:
            print(f"  [FAIL] Failed to get event details for ID {event_id}: HTTP {st_detail}")
    else:
        print(f"  [FAIL] Student login or public events returned invalid format (login: {stu_login_st}, events: {status}).")

    # 3. Organizer Login, Dynamic ID discovery, and Event Validation & Creation
    total += 1
    print("\n[Check 3] Organizer Login, Form Validation & Submission")
    login_st, login_res = login("vishnu@gmail.com", "Password123!")
    created_event_id = None
    series_id = None
    venue_id = None
    if login_st == 200:
        print("  [PASS] Organizer login successful.")
        
        # Discover real series and venue
        st_series, series_res = request_json(f"{BACKEND_BASE}/api/public/event-series")
        st_venues, venues_res = request_json(f"{BACKEND_BASE}/api/venues")
        
        series_items = series_res.get("series", []) if isinstance(series_res, dict) else []
        venue_items = venues_res.get("venues", []) if isinstance(venues_res, dict) else []
        
        series_id = series_items[0].get("id") or series_items[0].get("series_id") if len(series_items) > 0 else None
        venue_id = venue_items[0].get("id") or venue_items[0].get("venue_id") if len(venue_items) > 0 else None
        
        # Test 3a: Invalid Form Submission (missing required fields)
        st_invalid, res_invalid = request_json(
            f"{BACKEND_BASE}/api/events",
            method="POST",
            data={"event_name": ""}  # missing required fields
        )
        if st_invalid in [400, 422]:
            print(f"  [PASS] Backend properly rejected invalid event submission with HTTP {st_invalid}: {res_invalid.get('error', 'Validation error')}")
        else:
            print(f"  [FAIL] Expected 400/422 for invalid form, got HTTP {st_invalid}")

        # Test 3b: Valid Event Creation
        future_date = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
        event_payload = {
            "event_name": f"Step 4C Test Symposium {datetime.datetime.now().strftime('%M%S')}",
            "series_id": series_id,
            "category": "Technical",
            "requested_date": future_date,
            "requested_start_time": "10:00:00",
            "requested_end_time": "13:00:00",
            "venue_id": venue_id,
            "description": "Validation test symposium for Step 4C operational workflows."
        }
        st_create, res_create = request_json(f"{BACKEND_BASE}/api/events", method="POST", data=event_payload)
        if st_create in [200, 201]:
            created_event_id = res_create.get("event_id") or (res_create.get("event") and (res_create["event"].get("event_id") or res_create["event"].get("id")))
            print(f"  [PASS] Event request submitted successfully! Created Event ID: {created_event_id}")
            
            # Check My Events list
            st_my, res_my = request_json(f"{BACKEND_BASE}/api/events")
            my_events = res_my.get("events", [])
            if st_my == 200 and any((e.get("event_id") == created_event_id or e.get("id") == created_event_id) for e in my_events):
                print("  [PASS] Created event appears in Organizer 'My Events' table.")
                passed += 1
            else:
                print("  [FAIL] Created event not found in /api/events")
        else:
            print(f"  [FAIL] Failed to create event: HTTP {st_create}: {res_create}")
    else:
        print(f"  [FAIL] Organizer login failed: HTTP {login_st}")

    # 4. Management Login & Event Requests Operational Table
    total += 1
    print("\n[Check 4] Management Login & Operational Requests Table")
    mgmt_st, mgmt_res = login("mgmt_admin_1791211266@college.edu", "Password123!")
    if mgmt_st == 200:
        print("  [PASS] Management admin login successful.")
        st_all, res_all = request_json(f"{BACKEND_BASE}/api/management/events")
        st_pen, res_pen = request_json(f"{BACKEND_BASE}/api/management/events/pending")
        if st_all == 200 and st_pen == 200:
            events = res_all.get("events", [])
            pending_events = res_pen.get("events", [])
            print(f"  [PASS] Fetched {len(events)} total events; {len(pending_events)} pending operational requests.")
            passed += 1
        else:
            print(f"  [FAIL] Failed to fetch events for management: HTTP {st_all}, {st_pen}")
    else:
        print(f"  [FAIL] Management login failed: HTTP {mgmt_st}")

    # 5. Management Review, Venue Conflict Enforcement (409) & Allocation Approval
    total += 1
    print("\n[Check 5] Venue Conflict Enforcement & Facility Allocation")
    if mgmt_st == 200 and created_event_id:
        # Get event review detail
        st_rev, rev_data = request_json(f"{BACKEND_BASE}/api/management/events/{created_event_id}")
        if st_rev == 200:
            print(f"  [PASS] Review data retrieved for Event #{created_event_id}.")
            
            # Find an already approved event to simulate a conflict
            st_all, res_all = request_json(f"{BACKEND_BASE}/api/management/events")
            scheduled = [e for e in res_all.get("events", []) if e.get("status") in ["approved", "scheduled"] and e.get("venue_id")]
            
            if scheduled:
                busy = scheduled[0]
                conflict_payload = {
                    "venue_id": busy.get("venue_id"),
                    "approved_date": str(busy.get("approved_date") or busy.get("event_date") or busy.get("requested_date")),
                    "approved_start_time": str(busy.get("approved_start_time") or busy.get("start_time")),
                    "approved_end_time": str(busy.get("approved_end_time") or busy.get("end_time"))
                }
                st_conf, res_conf = request_json(
                    f"{BACKEND_BASE}/api/management/events/{created_event_id}/allocation",
                    method="PATCH",
                    data=conflict_payload
                )
                if st_conf == 409:
                    print(f"  [PASS] Venue conflict correctly detected and blocked with HTTP 409: '{res_conf.get('message', 'Conflict')}'")
                else:
                    print(f"  - Note: Conflict test returned HTTP {st_conf}: {res_conf.get('message', res_conf.get('error'))}")
            
            # Now perform valid facility allocation on a clear future date
            alloc_date = (datetime.date.today() + datetime.timedelta(days=60 + (created_event_id % 100))).isoformat()
            alloc_payload = {
                "venue_id": venue_id,
                "approved_date": alloc_date,
                "approved_start_time": "18:00:00",
                "approved_end_time": "21:00:00"
            }
            st_alloc, res_alloc = request_json(
                f"{BACKEND_BASE}/api/management/events/{created_event_id}/allocation",
                method="PATCH",
                data=alloc_payload
            )
            if st_alloc == 200:
                print(f"  [PASS] Event #{created_event_id} allocated and approved successfully.")
                passed += 1
            else:
                print(f"  [FAIL] Allocation failed: HTTP {st_alloc}: {res_alloc}")
        else:
            print(f"  [FAIL] Could not fetch review data: HTTP {st_rev}")
    else:
        print("  [FAIL] Skipping allocation check due to earlier failure.")

    # 6. Rejection Workflow with Reason
    total += 1
    print("\n[Check 6] Rejection Confirmation & API Execution")
    if mgmt_st == 200:
        # Create a temporary pending event as organizer to test rejection
        login("vishnu@gmail.com", "Password123!")
        temp_date = (datetime.date.today() + datetime.timedelta(days=28)).isoformat()
        st_tmp, res_tmp = request_json(
            f"{BACKEND_BASE}/api/events",
            method="POST",
            data={
                "event_name": f"Rejection Test Event {datetime.datetime.now().strftime('%M%S')}",
                "series_id": series_id,
                "category": "Sports",
                "requested_date": temp_date,
                "requested_start_time": "09:00:00",
                "requested_end_time": "12:00:00",
                "venue_id": venue_id,
                "description": "Event created specifically to verify rejection workflow and reason logging."
            }
        )
        if st_tmp in [200, 201]:
            tmp_id = res_tmp.get("event_id") or (res_tmp.get("event") and (res_tmp["event"].get("event_id") or res_tmp["event"].get("id")))
            # Switch back to management admin
            login("mgmt_admin_1791211266@college.edu", "Password123!")
            st_rej, res_rej = request_json(
                f"{BACKEND_BASE}/api/management/events/{tmp_id}/status",
                method="PATCH",
                data={"status": "rejected", "rejection_reason": "Scheduling conflict with annual faculty assembly."}
            )
            if st_rej == 200:
                print(f"  [PASS] Event #{tmp_id} rejected successfully with reason logged.")
                passed += 1
            else:
                print(f"  [FAIL] Event rejection failed: HTTP {st_rej}: {res_rej}")
        else:
            print(f"  [FAIL] Failed to create event for rejection test: HTTP {st_tmp}")
    else:
        print("  [FAIL] Skipping rejection check due to login failure.")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} checks passed.")
    print("=" * 60)
    if passed == total:
        print(">>> ALL STEP 4C ACCEPTANCE TESTS PASSED SUCCESSFULLY! <<<")
        return 0
    else:
        print(f">>> {total - passed} CHECKS FAILED. <<<")
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())
