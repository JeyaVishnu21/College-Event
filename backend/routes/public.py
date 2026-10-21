"""
Public Discovery Routes
-----------------------
Provides public, read-only event discovery endpoints for students and visitors.
Requires NO authentication. Exposes safe event schedules, venue info, festival series,
and high-level crowd counts without leaking passwords, alerts, or administrative metadata.
"""

from datetime import timedelta
from typing import Any
from flask import Blueprint, request, jsonify

from models.event import EventModel
from models.fest import FestModel, EventSeriesModel
from models.venue import VenueModel

public_bp = Blueprint('public', __name__)


def serialize_field(val: Any) -> Any:
    """Safely serialize date, time, datetime, and timedelta values for JSON responses."""
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
# 1. PUBLIC EVENTS DISCOVERY
# -------------------------------------------------------------
@public_bp.route('/events', methods=['GET'])
def get_public_events():
    """
    Search and filter public events.
    Supports query parameters:
      - search: Event name or description keyword
      - year: 4-digit year (e.g. 2026)
      - month: 1-12
      - category: Technical, Cultural, Sports, Arts, General, etc.
      - status: upcoming, ongoing, completed
      - series_id: filter by festival series
      - limit: optional result cap
    """
    search = request.args.get('search', '').strip() or None
    year_raw = request.args.get('year', '').strip()
    month_raw = request.args.get('month', '').strip()
    category = request.args.get('category', '').strip() or None
    status = request.args.get('status', '').strip() or None
    series_raw = request.args.get('series_id', '').strip()
    limit_raw = request.args.get('limit', '').strip()

    year = int(year_raw) if year_raw and year_raw.isdigit() else None
    month = int(month_raw) if month_raw and month_raw.isdigit() else None
    series_id = int(series_raw) if series_raw and series_raw.isdigit() else None
    limit = int(limit_raw) if limit_raw and limit_raw.isdigit() else None

    try:
        events = EventModel.get_public_events(
            search=search,
            year=year,
            month=month,
            category=category,
            status=status,
            series_id=series_id,
            limit=limit
        )

        formatted_events = []
        for e in events:
            formatted_events.append({
                "id": e['id'],
                "event_name": e['event_name'],
                "description": e['description'],
                "category": e.get('category') or 'General',
                "status": e.get('computed_status') or 'Upcoming',
                "raw_status": e.get('raw_status'),
                "start_date": serialize_field(e.get('start_date')),
                "end_date": serialize_field(e.get('end_date')),
                "start_time": serialize_field(e.get('start_time')),
                "end_time": serialize_field(e.get('end_time')),
                "venue_name": e.get('venue_name') or 'To be announced',
                "venue_location": e.get('venue_location') or '',
                "venue_capacity": e.get('venue_capacity'),
                "series_id": e.get('series_id'),
                "series_name": e.get('series_name'),
                "crowd_status": e.get('crowd_status'),
                "estimated_crowd": e.get('max_crowd')
            })

        return jsonify({
            "success": True,
            "count": len(formatted_events),
            "events": formatted_events
        }), 200

    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to retrieve public events. Please try again."
        }), 500


# -------------------------------------------------------------
# 2. PUBLIC EVENT DETAIL
# -------------------------------------------------------------
@public_bp.route('/events/<int:event_id>', methods=['GET'])
def get_public_event_detail(event_id: int):
    """
    Retrieve single public event details with complete crowd monitoring stats.
    Exposes only approved/completed events.
    Returns safe empty state if no crowd analysis exists.
    """
    try:
        event = EventModel.get_public_event_detail(event_id)
        if not event:
            return jsonify({
                "error": "Not Found",
                "message": f"Event with ID {event_id} was not found or is not open for public viewing."
            }), 404

        max_crowd = event.get('max_crowd')
        crowd_available = (max_crowd is not None)

        crowd_info = {
            "available": crowd_available,
            "estimated_crowd": max_crowd,
            "venue_capacity": event.get('venue_capacity'),
            "crowd_status": event.get('crowd_status'),
            "last_analyzed": serialize_field(event.get('latest_analyzed_at')),
            "message": None if crowd_available else "Crowd information is not available yet."
        }

        response_data = {
            "id": event['id'],
            "event_name": event['event_name'],
            "description": event['description'],
            "category": event.get('category') or 'General',
            "status": event.get('computed_status') or 'Upcoming',
            "raw_status": event.get('raw_status'),
            "start_date": serialize_field(event.get('start_date')),
            "end_date": serialize_field(event.get('end_date')),
            "start_time": serialize_field(event.get('start_time')),
            "end_time": serialize_field(event.get('end_time')),
            "venue_id": event.get('venue_id'),
            "venue_name": event.get('venue_name') or 'To be announced',
            "venue_location": event.get('venue_location') or '',
            "venue_capacity": event.get('venue_capacity'),
            "series_id": event.get('series_id'),
            "series_name": event.get('series_name'),
            "series_description": event.get('series_description'),
            "crowd_info": crowd_info
        }

        return jsonify({
            "success": True,
            "event": response_data
        }), 200

    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to load event details."
        }), 500


# -------------------------------------------------------------
# 3. FEST (EVENT SERIES) ENDPOINTS
# -------------------------------------------------------------
@public_bp.route('/fests', methods=['GET'])
@public_bp.route('/fest', methods=['GET'])
@public_bp.route('/event-series', methods=['GET'])
def get_public_fests():
    """Retrieve all campus fests with date ranges and event counts."""
    try:
        series_list = FestModel.get_all()
        return jsonify({
            "success": True,
            "count": len(series_list),
            "fests": serialize_data(series_list),
            "series": serialize_data(series_list)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to retrieve fests."
        }), 500

get_public_event_series = get_public_fests


@public_bp.route('/fests/<int:series_id>', methods=['GET'])
@public_bp.route('/fest/<int:series_id>', methods=['GET'])
@public_bp.route('/event-series/<int:series_id>', methods=['GET'])
def get_public_fest_detail(series_id: int):
    """Retrieve details for a single fest and all associated public events."""
    try:
        series = FestModel.get_series_with_events(series_id)
        if not series:
            return jsonify({
                "error": "Not Found",
                "message": f"Fest with ID {series_id} not found."
            }), 404

        return jsonify({
            "success": True,
            "fest": serialize_data(series),
            "series": serialize_data(series)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to load fest details."
        }), 500

get_public_series_detail = get_public_fest_detail


# -------------------------------------------------------------
# 4. FILTER METADATA (Categories and Years)
# -------------------------------------------------------------
@public_bp.route('/categories', methods=['GET'])
def get_public_categories_and_years():
    """Retrieve available categories and years for dynamic filter selectors."""
    try:
        categories = EventModel.get_public_categories()
        years = EventModel.get_public_years()
        return jsonify({
            "success": True,
            "categories": categories,
            "years": years
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to load filter metadata."
        }), 500


# -------------------------------------------------------------
# 5. PUBLIC VENUES WITH DIRECTIONS
# -------------------------------------------------------------
@public_bp.route('/venues', methods=['GET'])
def get_public_venues():
    """
    Retrieve all campus venues with locations, capacities, and walking directions.
    Accessible openly without authentication.
    """
    try:
        venues = VenueModel.get_all()

        directions_map = {
            "Main Auditorium": {
                "zone": "Central Campus",
                "landmark": "Near University Quadrangle Fountain",
                "directions": "Enter via Main University Gate. Walk past Administration Tower along the palm promenade; the Main Auditorium grand portico is on your right at Block A (1st Floor)."
            },
            "Fest Hall Alpha": {
                "zone": "West Academic Wing",
                "landmark": "Block C Student Center",
                "directions": "Proceed towards the West Wing past Student Cafeteria. Enter Block C entrance, take the central stairs or elevator to the 3rd Floor; Fest Hall Alpha is opposite Room C-302."
            },
            "Student Browsing Hall": {
                "zone": "Student Activity Complex",
                "landmark": "Adjacent to University Central Library",
                "directions": "From Central Campus Library plaza, take the covered walkway toward Block S. Enter the ground level archway and proceed up one flight of stairs to 1st Floor Hall."
            },
            "CSE SEMINOR HALL": {
                "zone": "Technology & Computing Block",
                "landmark": "Opposite Turing Computing Labs",
                "directions": "Enter East Campus Gate. Follow signs to Computer Science & Engineering Block. The Seminar Hall is located directly through the main lobby entrance on the ground floor."
            },
            "Innovation Lab": {
                "zone": "Science & Research Quad",
                "landmark": "Science Complex Block D",
                "directions": "Head to Science Quadrangle. Enter Science Block D foyer, take elevator to 3rd Floor; follow corridor east toward the Robotics & AI research wing."
            }
        }

        formatted = []
        for v in venues:
            name = v.get('name', '')
            matched_info = None
            for key, info in directions_map.items():
                if key.lower() in name.lower() or name.lower() in key.lower():
                    matched_info = info
                    break

            if not matched_info:
                matched_info = {
                    "zone": "Campus Academic Zone",
                    "landmark": v.get('location') or "Campus Main Building",
                    "directions": f"Navigate to {v.get('location') or 'designated campus block'}. Follow departmental directional signage to enter the hall."
                }

            formatted.append({
                "id": v['id'],
                "name": v['name'],
                "location": v.get('location') or 'Main Campus',
                "capacity": v.get('capacity') or 0,
                "status": v.get('status') or 'available',
                "zone": matched_info['zone'],
                "landmark": matched_info['landmark'],
                "directions": matched_info['directions']
            })

        return jsonify({
            "success": True,
            "count": len(formatted),
            "venues": formatted
        }), 200

    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": "Unable to load campus venues."
        }), 500

