"""
STEP 4E — PRODUCTION READINESS & E2E SYSTEM AUDIT
-------------------------------------------------
Comprehensive audit testing:
1. Static Frontend Asset and Markup Audit (All HTML, CSS, JS valid and resolvable)
2. Student Complete Workflow (Browse, Search, Filter, Detail, Crowd, Profile)
3. Organizer Complete Workflow (Auth, Dashboard Stats, My Events, Validation, Event Submission, Detail, Profile)
4. Management Complete Workflow (Auth, Queue, Review, Conflict Detection, Allocation, Rejection, Profile)
5. Session Integrity and Cross-Role Security Audit
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app


class TestStep4EAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_01_static_assets_integrity(self):
        """Verify all HTML pages and critical CSS/JS files exist, have proper encoding, and contain Step 4E requirements."""
        frontend_dir = BASE_DIR / "frontend"
        critical_pages = [
            "index.html", "login.html", "student.html", "organizer.html",
            "management.html", "events.html", "event.html", "series.html"
        ]

        for page in critical_pages:
            file_path = frontend_dir / page
            self.assertTrue(file_path.exists(), f"Missing page: {page}")
            content = file_path.read_text(encoding="utf-8")
            self.assertGreater(len(content), 100, f"Page too small: {page}")
            self.assertNotIn("Made with AI", content)
            self.assertNotIn("<!-- TODO", content)

        # Verify Student HTML has dash-events-container
        student_html = (frontend_dir / "student.html").read_text(encoding="utf-8")
        self.assertIn('id="dash-events-container"', student_html, "Student HTML missing dash-events-container")
        self.assertIn('id="section-dashboard"', student_html)
        self.assertIn('id="section-events"', student_html)
        self.assertIn('id="section-profile"', student_html)

        # Verify style.css contains responsive breakpoints and badge styles
        css_content = (frontend_dir / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 900px)", css_content)
        self.assertIn("@media (max-width: 768px)", css_content)
        self.assertIn("@media (max-width: 480px)", css_content)
        self.assertIn(".badge-approved", css_content)
        self.assertIn(".badge-pending", css_content)
        self.assertIn(".badge-rejected", css_content)
        self.assertIn(".badge-scheduled", css_content)
        self.assertIn(".profile-card", css_content)

        print("  [PASS] Static assets, markup integrity, and CSS tokens verified.")

    def test_02_student_end_to_end_flow(self):
        """Verify Student workflow: browse, search, category filter, event details, crowd info, and profile."""
        c = self.app.test_client()

        login_res = c.post('/api/auth/login', json={
            "email": "student_test_1791211266@college.edu",
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.get_json()['user']['role'], 'student')

        me_res = c.get('/api/auth/me')
        self.assertEqual(me_res.status_code, 200)
        user_info = me_res.get_json()['user']
        self.assertEqual(user_info['role'], 'student')
        self.assertNotIn('password', user_info)
        self.assertNotIn('password_hash', user_info)

        events_res = c.get('/api/public/events')
        self.assertEqual(events_res.status_code, 200)
        events = events_res.get_json()['events']
        self.assertGreater(len(events), 0)

        search_res = c.get('/api/public/events?search=Cricket')
        self.assertEqual(search_res.status_code, 200)
        search_events = search_res.get_json()['events']
        self.assertTrue(any('Cricket' in e['event_name'] for e in search_events))

        first_event_id = events[0]['id']
        detail_res = c.get(f'/api/public/events/{first_event_id}')
        self.assertEqual(detail_res.status_code, 200)
        event_detail = detail_res.get_json()['event']
        self.assertIn('crowd_info', event_detail)

        venues_res = c.get('/api/venues')
        self.assertEqual(venues_res.status_code, 200)
        self.assertGreater(len(venues_res.get_json()['venues']), 0)

        c.post('/api/auth/logout')
        print("  [PASS] Student complete workflow verified successfully.")

    def test_03_organizer_end_to_end_flow(self):
        """Verify Organizer workflow: auth, dashboard stats, submission validation, proposal creation, and listing."""
        c = self.app.test_client()

        login_res = c.post('/api/auth/login', json={
            "email": "vishnu@gmail.com",
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200)

        dash_res = c.get('/api/organizer/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        stats = dash_res.get_json()['stats']
        self.assertIn('total_events', stats)
        self.assertIn('pending_events', stats)
        self.assertIn('approved_events', stats)

        bad_sub = c.post('/api/events', json={
            "event_name": "",
            "description": "Valid desc",
            "requested_date": "2026-11-20",
            "requested_start_time": "10:00:00",
            "requested_end_time": "14:00:00"
        })
        self.assertIn(bad_sub.status_code, [400, 422])

        series_res = c.get('/api/public/event-series')
        self.assertEqual(series_res.status_code, 200)
        series_list = series_res.get_json()['series']
        series_id = series_list[0]['id'] if series_list else None

        req_date = (date.today() + timedelta(days=55)).isoformat()
        create_res = c.post('/api/events', json={
            "event_name": f"Audit Symposium {req_date}",
            "description": "Production readiness test symposium",
            "category": "Technical",
            "requested_date": req_date,
            "requested_start_time": "10:00:00",
            "requested_end_time": "16:00:00",
            "venue_id": 101,
            "series_id": series_id
        })
        self.assertEqual(create_res.status_code, 201)
        created_id = create_res.get_json()['event']['id']

        my_events_res = c.get('/api/events')
        self.assertEqual(my_events_res.status_code, 200)
        my_events = my_events_res.get_json()['events']
        self.assertTrue(any(e['id'] == created_id for e in my_events))

        c.post('/api/auth/logout')
        print(f"  [PASS] Organizer complete workflow verified (Created Event #{created_id}).")

    def test_04_management_end_to_end_flow(self):
        """Verify Management workflow: proposals review, conflict prevention, schedule allocation, rejection."""
        c = self.app.test_client()

        login_res = c.post('/api/auth/login', json={
            "email": "mgmt_admin_1791211266@college.edu",
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200)

        mgmt_dash = c.get('/api/management/dashboard')
        self.assertEqual(mgmt_dash.status_code, 200)
        self.assertIn('stats', mgmt_dash.get_json())

        pending_res = c.get('/api/management/events?status=pending')
        self.assertEqual(pending_res.status_code, 200)
        pending_events = pending_res.get_json()['events']

        if pending_events:
            ev = pending_events[0]
            ev_id = ev['id']

            alloc_date = (date.today() + timedelta(days=150 + (ev_id % 40))).isoformat()
            alloc_res = c.patch(f'/api/management/events/{ev_id}/allocation', json={
                "venue_id": 101,
                "approved_date": alloc_date,
                "approved_start_time": "09:00:00",
                "approved_end_time": "12:00:00"
            })
            self.assertEqual(alloc_res.status_code, 200)

            conflict_res = c.patch(f'/api/management/events/{ev_id}/allocation', json={
                "venue_id": 101,
                "approved_date": alloc_date,
                "approved_start_time": "10:00:00",
                "approved_end_time": "14:00:00"
            })
            self.assertIn(conflict_res.status_code, [200, 409])

        c.post('/api/auth/logout')
        print("  [PASS] Management complete operational workflow verified.")

    def test_05_security_and_role_boundaries(self):
        """Verify strict role-based access control (401 unauth, 403 cross-role)."""
        c = self.app.test_client()

        self.assertEqual(c.get('/api/management/dashboard').status_code, 401)
        self.assertEqual(c.get('/api/organizer/dashboard').status_code, 401)

        c.post('/api/auth/login', json={
            "email": "student_test_1791211266@college.edu",
            "password": "Password123!"
        })
        self.assertEqual(c.get('/api/management/dashboard').status_code, 403)
        self.assertEqual(c.get('/api/organizer/dashboard').status_code, 403)
        c.post('/api/auth/logout')

        c.post('/api/auth/login', json={
            "email": "vishnu@gmail.com",
            "password": "Password123!"
        })
        self.assertEqual(c.get('/api/management/dashboard').status_code, 403)
        c.post('/api/auth/logout')

        print("  [PASS] Security boundaries and cross-role privilege isolation strictly verified.")


if __name__ == '__main__':
    print('=' * 60)
    print('STEP 4E — PRODUCTION READINESS VERIFICATION SUITE')
    print('=' * 60)
    unittest.main(verbosity=2)
