"""
Comprehensive Test Suite: Stage 8 - Event Crowd Reports & PDF Audit Generation
-------------------------------------------------------------------------------
Verifies:
 1. Report for event with multiple successful crowd analyses (Event 9034)
 2. Verification of maximum crowd count calculation (762 persons)
 3. Report for event with no analyzed images (Event 9031)
 4. Proper classification of pending / failed image records
 5. Event with no alerts handled cleanly
 6. Nonexistent / invalid event ID returns HTTP 404
 7. Role isolation: Organizer cannot inspect another organizer's report (HTTP 403)
 8. Role authorization: Administrator / Management can inspect any report (HTTP 200)
 9. JSON API payload structure and property integrity
10. ReportLab PDF compilation and valid binary stream inspection (%PDF-)
11. Regression check: Existing auth, venue, and dashboard endpoints remain unaffected
"""

import io
import unittest
from datetime import datetime
from app import create_app
from models.report import ReportModel
from services.pdf_report import generate_pdf_report


class TestStage8Reports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

    # -------------------------------------------------------------
    # 1 & 2. Event with Multiple Analyses & Max Crowd Count
    # -------------------------------------------------------------
    def test_01_event_with_multiple_analyses(self):
        """Test report for event 9034 which has 5 completed analyses."""
        report = ReportModel.get_event_report(9034)
        self.assertIsNotNone(report, "Event 9034 report should exist")

        summary = report['summary']
        self.assertTrue(summary['has_data'], "Event 9034 should have data")
        self.assertEqual(summary['analyzed_images'], 5, "Should have 5 analyzed images")
        self.assertEqual(summary['max_crowd'], 762, "Maximum crowd count must be 762")
        self.assertEqual(summary['min_crowd'], 1, "Minimum crowd count must be 1")
        self.assertEqual(summary['venue_capacity'], 150, "Venue capacity must be 150")
        self.assertEqual(summary['peak_utilization_percent'], 508.0, "Utilization must be 508.0%")
        self.assertIn("Critical", summary['highest_crowd_level'], "Level should be Critical (Overcapacity)")

        # Verify chronological order
        history = report['history']
        self.assertEqual(len(history), 5, "History should have 5 items")
        timestamps = [h['analysis_timestamp'] for h in history]
        self.assertEqual(timestamps, sorted(timestamps), "History must be sorted chronologically")

    # -------------------------------------------------------------
    # 3. Event with No Analyzed Images
    # -------------------------------------------------------------
    def test_02_event_with_no_analyzed_images(self):
        """Test report for event 9031 which has no uploaded / analyzed images."""
        report = ReportModel.get_event_report(9031)
        self.assertIsNotNone(report, "Event 9031 report should exist")

        summary = report['summary']
        self.assertFalse(summary['has_data'], "Event 9031 should not have data")
        self.assertEqual(summary['analyzed_images'], 0)
        self.assertIsNone(summary['max_crowd'])
        self.assertIsNone(summary['peak_utilization_percent'])
        self.assertEqual(summary['highest_crowd_level'], "No Data")
        self.assertEqual(len(report['history']), 0)

    # -------------------------------------------------------------
    # 4. Pending / Failed Handling
    # -------------------------------------------------------------
    def test_03_summary_handles_pending_failed_counters(self):
        """Verify summary dictionary explicitly provides counters for all states."""
        report = ReportModel.get_event_report(9034)
        summary = report['summary']
        self.assertIn('pending_images', summary)
        self.assertIn('failed_images', summary)
        self.assertIn('total_images', summary)

    # -------------------------------------------------------------
    # 5. Event with No Alerts
    # -------------------------------------------------------------
    def test_04_event_with_no_alerts(self):
        """Verify events without alerts return empty list and count 0."""
        report = ReportModel.get_event_report(9034)
        self.assertEqual(report['summary']['alerts_count'], 0)
        self.assertEqual(report['alerts'], [])

    # -------------------------------------------------------------
    # 6. Nonexistent Event ID (HTTP 404)
    # -------------------------------------------------------------
    def test_05_nonexistent_event_id(self):
        """Test that requesting an invalid or nonexistent event ID returns HTTP 404."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1  # admin

        res = self.client.get('/api/reports/events/999999')
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json.get('message', '').lower())

    # -------------------------------------------------------------
    # 7. Role Isolation: Organizer Cannot Access Other Organizer's Report
    # -------------------------------------------------------------
    def test_06_organizer_cross_access_forbidden(self):
        """Verify an organizer cannot access another organizer's report (HTTP 403)."""
        # User 2 is organizer Alice; event 9034 belongs to Karikol (user 86)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2

        res = self.client.get('/api/reports/events/9034')
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.json.get('message', ''))

        # Also for PDF
        res_pdf = self.client.get('/api/reports/events/9034/pdf')
        self.assertEqual(res_pdf.status_code, 403)

    # -------------------------------------------------------------
    # 8. Authorized Access: Owner & Admin
    # -------------------------------------------------------------
    def test_07_authorized_access_permitted(self):
        """Verify event owner and administrators can access reports (HTTP 200)."""
        # A) Owner access
        with self.client.session_transaction() as sess:
            sess['user_id'] = 86  # Karikol owns 9034

        res_owner = self.client.get('/api/reports/events/9034')
        self.assertEqual(res_owner.status_code, 200)
        self.assertEqual(res_owner.json['report']['event']['id'], 9034)

        # B) Administrator access
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1  # Admin

        res_admin = self.client.get('/api/reports/events/9034')
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.json['report']['event']['id'], 9034)

    # -------------------------------------------------------------
    # 9. Accessible Events Listing Filtered by Role
    # -------------------------------------------------------------
    def test_08_accessible_events_listing(self):
        """Verify /api/reports/events lists all events for admin and only owned for organizer."""
        # Admin gets all events
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
        res_admin = self.client.get('/api/reports/events')
        self.assertEqual(res_admin.status_code, 200)
        all_events = res_admin.json['events']
        self.assertGreaterEqual(len(all_events), 1)

        # Organizer gets only their own events
        with self.client.session_transaction() as sess:
            sess['user_id'] = 86
        res_org = self.client.get('/api/reports/events')
        self.assertEqual(res_org.status_code, 200)
        org_events = res_org.json['events']
        for ev in org_events:
            self.assertEqual(ev['organizer_id'], 86)

    # -------------------------------------------------------------
    # 10. PDF Generation & Valid Stream
    # -------------------------------------------------------------
    def test_09_pdf_generation_content_and_stream(self):
        """Verify PDF generation creates valid binary PDF files for data and empty states."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1

        # A) Event 9034 (with data & timeline chart)
        res = self.client.get('/api/reports/events/9034/pdf')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'application/pdf')
        pdf_data = res.data
        self.assertTrue(pdf_data.startswith(b'%PDF-'), "File must begin with %PDF- magic bytes")
        self.assertGreater(len(pdf_data), 10000, "PDF with chart and tables should be > 10KB")

        # B) Event 9031 (with no analysis data)
        res_empty = self.client.get('/api/reports/events/9031/pdf')
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(res_empty.headers.get('Content-Type'), 'application/pdf')
        self.assertTrue(res_empty.data.startswith(b'%PDF-'))

    # -------------------------------------------------------------
    # 11. Regression Check: Existing Features Still Work
    # -------------------------------------------------------------
    def test_10_regression_check(self):
        """Verify existing core endpoints continue functioning normally."""
        # Health check
        res_h = self.client.get('/api/health')
        self.assertEqual(res_h.status_code, 200)

        # Venues listing
        res_v = self.client.get('/api/venues')
        self.assertEqual(res_v.status_code, 200)

        # Dashboard endpoints
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
        res_dash = self.client.get('/api/administrator/dashboard')
        self.assertEqual(res_dash.status_code, 200)


if __name__ == '__main__':
    unittest.main()
