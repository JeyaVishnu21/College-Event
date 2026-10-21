"""
Report Generation Routes (Stage 8)
----------------------------------
Provides API endpoints for crowd occupancy and peak density reports.
Supports real-time report summaries, chronological analysis history,
threshold alerts audit logs, and downloadable official PDF reports.
"""

from decimal import Decimal
from datetime import date, time, datetime, timedelta
from typing import Any
from flask import Blueprint, jsonify, g, session, send_file, request

from middleware.auth import require_auth
from models.report import ReportModel
from services.pdf_report import generate_pdf_report

reports_bp = Blueprint('reports', __name__)


def serialize_field(val: Any) -> Any:
    """Serializes date, time, datetime, timedelta, and Decimal values cleanly for JSON."""
    if isinstance(val, (date, time, datetime)):
        return val.isoformat()
    if isinstance(val, timedelta):
        total_sec = int(val.total_seconds())
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if isinstance(val, Decimal):
        return float(val)
    return val


def serialize_data(obj: Any) -> Any:
    """Recursively serializes nested dictionary and list structures."""
    if isinstance(obj, list):
        return [serialize_data(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_field(v) for k, v in obj.items()}
    return serialize_field(obj)


# --------------------------------------------------------------------------
# 1. LIST EVENTS ACCESSIBLE FOR REPORTING
# --------------------------------------------------------------------------
@reports_bp.route('/reports/events', methods=['GET'])
@require_auth
def get_report_events():
    """
    Retrieves all events accessible to the authenticated user for reporting.
    Organizers are strictly limited to their own events.
    College administrators and management can review all events.
    """
    user_id = g.current_user.get('id')
    user_role = g.current_user.get('role', 'organizer')

    try:
        events = ReportModel.get_accessible_events(user_id=user_id, role=user_role)
        return jsonify({
            "status": "success",
            "events": serialize_data(events)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Unable to load events list for reporting: {str(exc)}"
        }), 500


# --------------------------------------------------------------------------
# 2. GET EVENT REPORT (JSON)
# --------------------------------------------------------------------------
@reports_bp.route('/reports/events/<int:event_id>', methods=['GET'])
@require_auth
def get_event_report(event_id: int):
    """
    Retrieves the complete crowd analytics report for a specific event.
    Returns event info, crowd summary statistics, chronological history, and alerts.
    """
    user_id = g.current_user.get('id')
    user_role = g.current_user.get('role', 'organizer')

    try:
        report = ReportModel.get_event_report(event_id)
        if not report:
            return jsonify({
                "error": "Not Found",
                "message": f"Event with ID {event_id} was not found."
            }), 404

        # Enforce role-based isolation: organizers can only view their own events
        if user_role == 'organizer':
            event_organizer_id = report.get('event', {}).get('organizer_id')
            if event_organizer_id != user_id:
                return jsonify({
                    "error": "Forbidden",
                    "message": "Access denied. You are only permitted to inspect reports for your own events."
                }), 403

        return jsonify({
            "status": "success",
            "report": serialize_data(report)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Unable to generate crowd report: {str(exc)}"
        }), 500


# --------------------------------------------------------------------------
# 3. DOWNLOAD OFFICIAL PDF REPORT
# --------------------------------------------------------------------------
@reports_bp.route('/reports/events/<int:event_id>/pdf', methods=['GET'])
@require_auth
def download_event_report_pdf(event_id: int):
    """
    Generates and streams an official PDF crowd report for the specified event.
    Includes event metadata, executive KPI summary, chronological history, and density chart.
    """
    user_id = g.current_user.get('id')
    user_role = g.current_user.get('role', 'organizer')

    try:
        report = ReportModel.get_event_report(event_id)
        if not report:
            return jsonify({
                "error": "Not Found",
                "message": f"Event with ID {event_id} was not found."
            }), 404

        # Enforce role-based isolation
        if user_role == 'organizer':
            event_organizer_id = report.get('event', {}).get('organizer_id')
            if event_organizer_id != user_id:
                return jsonify({
                    "error": "Forbidden",
                    "message": "Access denied. You are only permitted to download reports for your own events."
                }), 403

        # Generate PDF buffer using ReportLab
        pdf_buffer = generate_pdf_report(report)
        filename = f"crowd_audit_report_event_{event_id}.pdf"

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Failed to compile PDF report: {str(exc)}"
        }), 500
