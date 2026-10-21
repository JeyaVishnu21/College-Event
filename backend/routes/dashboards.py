"""
Dashboard Routes (Stage 5)
--------------------------
Provides role-isolated, real-time dashboard data for Event Organizers
and College Management. All metrics and lists are computed dynamically
from the MySQL database without static or hardcoded values.
"""

from datetime import timedelta
from typing import Any
from flask import Blueprint, jsonify, session, g, request
from middleware.auth import require_role
from models.event import EventModel
from models.venue import VenueModel

dashboards_bp = Blueprint('dashboards', __name__)


def serialize_field(val: Any) -> Any:
    """Serializes date, time, datetime, and timedelta values safely for JSON."""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    if isinstance(val, timedelta):
        total_sec = int(val.total_seconds())
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return val


def serialize_data(obj: Any) -> Any:
    """Recursively serializes list and dict structures."""
    if isinstance(obj, list):
        return [serialize_data(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_field(v) for k, v in obj.items()}
    return serialize_field(obj)


# -------------------------------------------------------------
# ORGANIZER DASHBOARD ENDPOINT
# -------------------------------------------------------------

@dashboards_bp.route('/organizer/dashboard', methods=['GET'])
@require_role('organizer')
def get_organizer_dashboard():
    """
    Retrieves real-time dashboard data for the authenticated organizer.
    Strictly isolated: queries using session['user_id'].
    Returns summary stats, all organizer events, and upcoming events.
    """
    try:
        organizer_id = session['user_id']

        # Real database aggregations
        stats = EventModel.get_organizer_statistics(organizer_id)
        events = EventModel.get_by_organizer(organizer_id)
        upcoming_events = EventModel.get_upcoming_approved_events(limit=5, organizer_id=organizer_id)

        from datetime import datetime
        now_tz = datetime.now().astimezone()
        return jsonify({
            "status": "success",
            "role": "organizer",
            "server_now": now_tz.isoformat(),
            "server_date": now_tz.strftime('%Y-%m-%d'),
            "server_time": now_tz.strftime('%H:%M:%S'),
            "timezone": now_tz.tzname() or "UTC",
            "timezone_offset": now_tz.strftime('%z'),
            "stats": stats,
            "events": serialize_data(events),
            "upcoming_events": serialize_data(upcoming_events)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to load dashboard data. Please try again."
        }), 500


# -------------------------------------------------------------
# ADMINISTRATOR DASHBOARD ENDPOINT
# -------------------------------------------------------------

@dashboards_bp.route('/administrator/dashboard', methods=['GET'])
@dashboards_bp.route('/management/dashboard', methods=['GET'])
@require_role('administrator')
def get_administrator_dashboard():
    """
    Retrieves system-wide real-time dashboard data for College Administrator.
    Returns summary metrics, pending event requests, upcoming events,
    and venue overview with available/unavailable counts.
    """
    try:
        # Real database calculations
        event_stats = EventModel.get_administrator_statistics()
        venue_stats = VenueModel.get_venue_statistics()

        # Combined stats dictionary for clean frontend consumption
        stats = {
            "total_events": event_stats["total_events"],
            "pending_events": event_stats["pending_events"],
            "pending_requests": event_stats["pending_events"],
            "approved_events": event_stats["approved_events"],
            "rejected_events": event_stats["rejected_events"],
            "upcoming_events": event_stats["upcoming_events"],
            "total_venues": venue_stats["total_venues"],
            "available_venues": venue_stats["available_venues"],
            "unavailable_venues": venue_stats["unavailable_venues"],
        }

        pending_requests = EventModel.get_pending_requests()
        upcoming_events = EventModel.get_upcoming_approved_events(limit=10)
        venues = VenueModel.get_all()

        return jsonify({
            "status": "success",
            "role": g.current_user.get('role', 'administrator'),
            "stats": stats,
            "pending_requests": serialize_data(pending_requests),
            "upcoming_events": serialize_data(upcoming_events),
            "venues": serialize_data(venues)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to load dashboard data. Please try again."
        }), 500


get_management_dashboard = get_administrator_dashboard

