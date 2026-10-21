"""
Event Routes (Stage 4)
----------------------
Handles event request creation, isolated organizer event viewing,
management event review, approval/rejection, and conflict-checked schedule allocation.
"""

from datetime import datetime, time
from typing import Optional, Tuple
from flask import Blueprint, request, jsonify, session, g
from middleware.auth import require_auth, require_role
from models.event import EventModel
from models.venue import VenueModel
from models.fest import FestModel, EventSeriesModel

events_bp = Blueprint('events', __name__)


def parse_time_str(time_str: str) -> Optional[time]:
    """Helper to parse time string in HH:MM or HH:MM:SS format."""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(time_str.strip(), fmt).time()
        except ValueError:
            pass
    return None


def validate_schedule_times(start_str: str, end_str: str) -> Tuple[bool, Optional[str]]:
    """Validates that start and end time strings exist and start < end."""
    start_t = parse_time_str(start_str)
    end_t = parse_time_str(end_str)

    if not start_t or not end_t:
        return False, "Times must be valid in HH:MM or HH:MM:SS format."

    if start_t >= end_t:
        return False, "Event start time must precede end time."

    return True, None


def validate_date_str(date_str: str) -> bool:
    """Helper to validate ISO date format (YYYY-MM-DD)."""
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


# -------------------------------------------------------------
# ORGANIZER EVENT ENDPOINTS
# -------------------------------------------------------------

@events_bp.route('/events', methods=['POST'])
@require_role('organizer')
def create_event_request():
    """
    Submits a new event request.
    Strictly associates event with session['user_id'].
    Initial status is set to 'pending'.
    """
    data = request.get_json(silent=True) or {}

    event_name = str(data.get('event_name', '')).strip()
    description = str(data.get('description', '')).strip()
    requested_date = str(data.get('requested_date', '')).strip()
    requested_start_time = str(data.get('requested_start_time', '')).strip()
    requested_end_time = str(data.get('requested_end_time', '')).strip()
    category = str(data.get('category', 'General')).strip() or 'General'
    preferred_venue_id = data.get('venue_id')
    if preferred_venue_id == '':
        preferred_venue_id = None

    if not event_name:
        return jsonify({"error": "Bad Request", "message": "Event name is required."}), 400

    if len(event_name) > 150:
        return jsonify({"error": "Bad Request", "message": "Event name cannot exceed 150 characters."}), 400

    if not requested_date or not validate_date_str(requested_date):
        return jsonify({"error": "Bad Request", "message": "Requested date must be in YYYY-MM-DD format."}), 400

    valid_times, time_err = validate_schedule_times(requested_start_time, requested_end_time)
    if not valid_times:
        return jsonify({"error": "Bad Request", "message": time_err}), 400

    # If preferred venue given, verify it exists
    if preferred_venue_id is not None:
        try:
            preferred_venue_id = int(preferred_venue_id)
            if not VenueModel.get_by_id(preferred_venue_id):
                return jsonify({"error": "Bad Request", "message": f"Venue with ID {preferred_venue_id} does not exist."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Bad Request", "message": "Invalid venue ID."}), 400

    # Fest / Event Series validation (Strictly required)
    series_id_raw = data.get('series_id')
    if series_id_raw is None or str(series_id_raw).strip() == '':
        return jsonify({"error": "Bad Request", "message": "Fest selection is required. Please select a Fest."}), 400

    try:
        series_id = int(series_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Bad Request", "message": "Invalid Fest ID. series_id must be a valid integer."}), 400

    fest = FestModel.get_by_id(series_id)
    if not fest:
        return jsonify({"error": "Bad Request", "message": f"Fest with ID {series_id} does not exist."}), 400

    # User ID strictly from session context, preventing client spoofing
    organizer_id = session['user_id']

    try:
        event_id = EventModel.create_event_request(
            organizer_id=organizer_id,
            event_name=event_name,
            description=description,
            requested_date=requested_date,
            requested_start_time=requested_start_time,
            requested_end_time=requested_end_time,
            venue_id=preferred_venue_id,
            category=category,
            series_id=series_id
        )
        created_event = EventModel.get_by_id(event_id)
        return jsonify({
            "message": "Event request submitted successfully.",
            "event": created_event
        }), 201
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500


@events_bp.route('/events', methods=['GET'])
@require_role('organizer')
def get_organizer_events():
    """
    Retrieve all events belonging to the authenticated organizer.
    Strictly isolated to the logged-in organizer.
    """
    organizer_id = session['user_id']
    events = EventModel.get_by_organizer(organizer_id)
    return jsonify({"events": events}), 200


@events_bp.route('/events/<int:event_id>', methods=['GET'])
@require_auth
def get_event_details(event_id: int):
    """
    Retrieve details for a single event.
    If requested by an organizer, strictly enforces ownership.
    Management users can inspect any event.
    """
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({"error": "Not Found", "message": f"Event with ID {event_id} not found."}), 404

    # Ownership enforcement for organizer role
    if g.current_user['role'] == 'organizer':
        if event['organizer_id'] != session['user_id']:
            return jsonify({
                "error": "Forbidden", 
                "message": "Access denied. You are only permitted to view your own events."
            }), 403

    return jsonify({"event": event}), 200


# -------------------------------------------------------------
# ADMINISTRATOR EVENT ENDPOINTS
# -------------------------------------------------------------

@events_bp.route('/administrator/events', methods=['GET'])
@events_bp.route('/management/events', methods=['GET'])
@require_role('administrator')
def administrator_get_all_events():
    """Retrieve all events across all organizers for administrator overview."""
    events = EventModel.get_all()
    return jsonify({"events": events}), 200

management_get_all_events = administrator_get_all_events


@events_bp.route('/administrator/events/pending', methods=['GET'])
@events_bp.route('/management/events/pending', methods=['GET'])
@require_role('administrator')
def administrator_get_pending_events():
    """Retrieve all pending event requests awaiting administrator review."""
    pending_events = EventModel.get_pending_requests()
    return jsonify({"events": pending_events}), 200

management_get_pending_events = administrator_get_pending_events


@events_bp.route('/administrator/events/<int:event_id>', methods=['GET'])
@events_bp.route('/management/events/<int:event_id>', methods=['GET'])
@require_role('administrator')
def administrator_get_event(event_id: int):
    """Retrieve complete event record for administrator review."""
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({"error": "Not Found", "message": f"Event with ID {event_id} not found."}), 404
    return jsonify({"event": event}), 200

management_get_event = administrator_get_event


@events_bp.route('/administrator/events/<int:event_id>/status', methods=['PATCH'])
@events_bp.route('/management/events/<int:event_id>/status', methods=['PATCH'])
@require_role('administrator')
def administrator_update_status(event_id: int):
    """
    Approve or reject an event request.
    When rejecting, an optional rejection_reason may be provided.
    """
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({"error": "Not Found", "message": f"Event with ID {event_id} not found."}), 404

    data = request.get_json(silent=True) or {}
    status = str(data.get('status', '')).strip().lower()
    rejection_reason = data.get('rejection_reason')

    if status not in EventModel.STATUSES:
        return jsonify({
            "error": "Bad Request", 
            "message": f"Invalid status '{status}'. Allowed statuses: {EventModel.STATUSES}."
        }), 400

    EventModel.update_status(event_id, status, rejection_reason)
    updated_event = EventModel.get_by_id(event_id)
    return jsonify({
        "message": f"Event status updated to '{status}'.",
        "event": updated_event
    }), 200

management_update_status = administrator_update_status


@events_bp.route('/administrator/events/<int:event_id>/allocation', methods=['PATCH'])
@events_bp.route('/management/events/<int:event_id>/allocation', methods=['PATCH'])
@require_role('administrator')
def administrator_allocate_schedule(event_id: int):
    """
    Allocate or modify the final venue and schedule for an event.
    Requirements:
      1. Event exists.
      2. Venue exists.
      3. Venue is currently available.
      4. Start time must precede end time.
      5. No conflicting approved event at that venue during the time range.
      6. Preserves organizer's original requested values.
    """
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({"error": "Not Found", "message": f"Event with ID {event_id} not found."}), 404

    data = request.get_json(silent=True) or {}

    venue_id_raw = data.get('venue_id')
    approved_date = str(data.get('approved_date', '')).strip()
    approved_start_time = str(data.get('approved_start_time', '')).strip()
    approved_end_time = str(data.get('approved_end_time', '')).strip()

    if venue_id_raw is None:
        return jsonify({"error": "Bad Request", "message": "venue_id is required."}), 400

    try:
        venue_id = int(venue_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Bad Request", "message": "venue_id must be an integer."}), 400

    # 1. Verify venue exists
    venue = VenueModel.get_by_id(venue_id)
    if not venue:
        return jsonify({"error": "Bad Request", "message": f"Venue with ID {venue_id} does not exist."}), 400

    # 2. Verify venue is available
    if venue['status'] != 'available':
        return jsonify({
            "error": "Bad Request", 
            "message": f"Cannot allocate venue '{venue['name']}': it is currently marked as unavailable."
        }), 400

    # 3. Verify date and times
    if not approved_date or not validate_date_str(approved_date):
        return jsonify({"error": "Bad Request", "message": "Approved date must be in YYYY-MM-DD format."}), 400

    valid_times, time_err = validate_schedule_times(approved_start_time, approved_end_time)
    if not valid_times:
        return jsonify({"error": "Bad Request", "message": time_err}), 400

    # 4. Validate venue capacity against event's expected participants
    expected_participants = data.get('expected_participants')
    if expected_participants is None:
        expected_participants = event.get('expected_participants')

    parsed_expected = None
    if expected_participants is not None and str(expected_participants).strip() != '':
        try:
            parsed_expected = int(expected_participants)
            if parsed_expected < 0:
                return jsonify({"error": "Bad Request", "message": "Expected participants must be a non-negative number."}), 400
            venue_cap = venue.get('capacity', 0)
            if venue_cap > 0 and parsed_expected > venue_cap:
                return jsonify({
                    "error": "Bad Request",
                    "message": (
                        f"Venue '{venue['name']}' capacity ({venue_cap}) is insufficient for the event's "
                        f"expected participants ({parsed_expected})."
                    )
                }), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Bad Request", "message": "Expected participants must be a valid integer."}), 400

    # 5. Conflict Check: verify no overlapping approved events at this venue on this date
    conflict = VenueModel.check_conflict(
        venue_id=venue_id,
        date_str=approved_date,
        start_time_str=approved_start_time,
        end_time_str=approved_end_time,
        exclude_event_id=event_id
    )
    if conflict:
        return jsonify({
            "error": "Conflict",
            "message": (
                f"Scheduling conflict: Venue '{venue['name']}' is already allocated to event "
                f"'{conflict['event_name']}' on {conflict['approved_date']} from "
                f"{str(conflict['approved_start_time'])} to {str(conflict['approved_end_time'])}."
            )
        }), 409

    # 6. Apply final allocation and set status to 'approved'
    try:
        EventModel.allocate_schedule(
            event_id=event_id,
            venue_id=venue_id,
            approved_date=approved_date,
            approved_start_time=approved_start_time,
            approved_end_time=approved_end_time,
            expected_participants=parsed_expected
        )
        updated_event = EventModel.get_by_id(event_id)
        return jsonify({
            "message": "Final venue and schedule allocated successfully.",
            "event": updated_event
        }), 200
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500
