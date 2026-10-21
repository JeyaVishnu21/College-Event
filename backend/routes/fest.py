"""
Fest Administrator Routes
-------------------------
Administrator CRUD endpoints for fests.
Requires 'administrator' role authentication.
"""

from datetime import datetime, date, timedelta
from typing import Optional, Any
from flask import Blueprint, request, jsonify
from middleware.auth import require_role
from models.fest import FestModel, EventSeriesModel

fest_bp = Blueprint('fest', __name__)


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


def validate_date_str(date_str: str) -> bool:
    """Helper to validate ISO date format (YYYY-MM-DD)."""
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except (ValueError, TypeError, AttributeError):
        return False


# -------------------------------------------------------------
# ADMINISTRATOR FEST CRUD ENDPOINTS
# -------------------------------------------------------------

@fest_bp.route('/administrator/fests', methods=['GET'])
@fest_bp.route('/administrator/fest', methods=['GET'])
@fest_bp.route('/management/event-series', methods=['GET'])
@require_role('administrator')
def list_administrator_fests():
    """
    Retrieve all fests for Administrator overview.
    Includes active/total event count and logical status (upcoming, ongoing, completed).
    """
    try:
        series_list = FestModel.get_administrator_list()
        return jsonify({
            "success": True,
            "count": len(series_list),
            "series": serialize_data(series_list),
            "fests": serialize_data(series_list)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Unable to retrieve fests: {str(exc)}"
        }), 500

list_management_event_series = list_administrator_fests


@fest_bp.route('/administrator/fests', methods=['POST'])
@fest_bp.route('/administrator/fest', methods=['POST'])
@fest_bp.route('/management/event-series', methods=['POST'])
@require_role('administrator')
def create_administrator_fest():
    """
    Create a new fest banner.
    Validations:
      - name is required (max 150 chars)
      - name must not duplicate an existing fest (case-insensitive)
      - start_date is optional (YYYY-MM-DD if provided)
      - end_date is optional (YYYY-MM-DD if provided)
      - end_date must not precede start_date if both are provided
      - trim whitespace
    """
    data = request.get_json(silent=True) or {}

    name = str(data.get('name', '')).strip()
    description = str(data.get('description', '')).strip() if data.get('description') is not None else None
    start_date = str(data.get('start_date', '')).strip()
    end_date = str(data.get('end_date', '')).strip()

    if not name:
        return jsonify({"error": "Bad Request", "message": "Fest name is required."}), 400

    if len(name) > 150:
        return jsonify({"error": "Bad Request", "message": "Fest name cannot exceed 150 characters."}), 400

    # Duplicate check
    existing_fest = FestModel.get_by_name(name)
    if existing_fest:
        return jsonify({"error": "Bad Request", "message": f"A fest named '{name}' already exists."}), 400

    # Validate start_date if provided
    if start_date:
        if not validate_date_str(start_date):
            return jsonify({"error": "Bad Request", "message": "Start date must be in YYYY-MM-DD format."}), 400
    else:
        start_date = None

    # Validate end_date if provided
    if end_date:
        if not validate_date_str(end_date):
            return jsonify({"error": "Bad Request", "message": "End date must be in YYYY-MM-DD format."}), 400
    else:
        end_date = None

    # Legacy endpoint backwards compatibility: require both dates if requested through /api/management/event-series
    if request.path.startswith('/api/management/event-series') and (not start_date or not end_date):
        return jsonify({"error": "Bad Request", "message": "Both start date and end date are required for event series."}), 400

    if start_date and end_date:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        if end_d < start_d:
            return jsonify({"error": "Bad Request", "message": "End date must not be earlier than start date."}), 400

    try:
        series_id = FestModel.create(
            name=name,
            description=description if description else None,
            start_date=start_date,
            end_date=end_date
        )
        created_series = FestModel.get_by_id(series_id)
        return jsonify({
            "success": True,
            "message": f"Fest '{name}' created successfully.",
            "series": serialize_data(created_series),
            "fest": serialize_data(created_series)
        }), 201
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500

create_management_event_series = create_administrator_fest


@fest_bp.route('/administrator/fests/<int:series_id>', methods=['GET'])
@fest_bp.route('/administrator/fest/<int:series_id>', methods=['GET'])
@fest_bp.route('/management/event-series/<int:series_id>', methods=['GET'])
@require_role('administrator')
def get_administrator_fest(series_id: int):
    """Retrieve details for a single fest by ID, including its approved events."""
    try:
        series = FestModel.get_by_id(series_id)
        if not series:
            return jsonify({
                "error": "Not Found",
                "message": f"Fest with ID {series_id} not found."
            }), 404

        approved_events = FestModel.get_fest_approved_events(series_id)

        return jsonify({
            "success": True,
            "series": serialize_data(series),
            "fest": serialize_data(series),
            "approved_events": serialize_data(approved_events),
            "events": serialize_data(approved_events)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Unable to load fest details: {str(exc)}"
        }), 500

get_management_event_series = get_administrator_fest


@fest_bp.route('/administrator/fests/<int:series_id>/approved-events', methods=['GET'])
@require_role('administrator')
def get_fest_approved_events_endpoint(series_id: int):
    """Retrieve approved events belonging to the specified fest."""
    try:
        series = FestModel.get_by_id(series_id)
        if not series:
            return jsonify({
                "error": "Not Found",
                "message": f"Fest with ID {series_id} not found."
            }), 404

        approved_events = FestModel.get_fest_approved_events(series_id)
        return jsonify({
            "success": True,
            "fest": serialize_data(series),
            "events": serialize_data(approved_events)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Unable to load approved events: {str(exc)}"
        }), 500


@fest_bp.route('/administrator/events/unassigned-approved', methods=['GET'])
@require_role('administrator')
def get_unassigned_approved_events_endpoint():
    """Retrieve approved events that currently have no fest assigned (series_id IS NULL)."""
    try:
        unassigned = FestModel.get_unassigned_approved_events()
        return jsonify({
            "success": True,
            "count": len(unassigned),
            "events": serialize_data(unassigned)
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Unable to load unassigned events: {str(exc)}"
        }), 500


@fest_bp.route('/administrator/events/<int:event_id>/assign-fest', methods=['PATCH', 'POST'])
@require_role('administrator')
def assign_event_to_fest_endpoint(event_id: int):
    """Safely associate an event with a fest, or unlink it."""
    from models.event import EventModel
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({"error": "Not Found", "message": f"Event with ID {event_id} not found."}), 404

    data = request.get_json(silent=True) or {}
    series_id_raw = data.get('series_id')

    series_id = None
    if series_id_raw is not None and str(series_id_raw).strip() != '':
        try:
            series_id = int(series_id_raw)
            fest = FestModel.get_by_id(series_id)
            if not fest:
                return jsonify({"error": "Bad Request", "message": f"Fest with ID {series_id} does not exist."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Bad Request", "message": "series_id must be a valid integer."}), 400

    try:
        FestModel.assign_event_to_fest(event_id, series_id)
        updated_event = EventModel.get_by_id(event_id)
        fest_name = FestModel.get_by_id(series_id)['name'] if series_id else 'None'
        return jsonify({
            "success": True,
            "message": f"Event '{event['event_name']}' successfully assigned to fest '{fest_name}'.",
            "event": serialize_data(updated_event)
        }), 200
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500


@fest_bp.route('/administrator/fests/<int:series_id>', methods=['PATCH', 'PUT'])
@fest_bp.route('/administrator/fest/<int:series_id>', methods=['PATCH', 'PUT'])
@fest_bp.route('/management/event-series/<int:series_id>', methods=['PATCH', 'PUT'])
@require_role('administrator')
def update_administrator_fest(series_id: int):
    """
    Update an existing fest record.
    Supports both partial updates (PATCH) and full updates (PUT).
    Applies the same strict validations as creation.
    """
    series = FestModel.get_by_id(series_id)
    if not series:
        return jsonify({
            "error": "Not Found",
            "message": f"Fest with ID {series_id} not found."
        }), 404

    data = request.get_json(silent=True) or {}

    # Extract or fallback to existing values
    name = str(data.get('name', series['name'])).strip() if 'name' in data else series['name']

    if 'description' in data:
        desc_val = data.get('description')
        description = str(desc_val).strip() if desc_val is not None else None
    else:
        description = series['description']

    start_date = str(data.get('start_date', series.get('start_date') or '')).strip() if 'start_date' in data else (str(series['start_date']) if series.get('start_date') else None)
    end_date = str(data.get('end_date', series.get('end_date') or '')).strip() if 'end_date' in data else (str(series['end_date']) if series.get('end_date') else None)

    if not name:
        return jsonify({"error": "Bad Request", "message": "Fest name is required."}), 400

    if len(name) > 150:
        return jsonify({"error": "Bad Request", "message": "Fest name cannot exceed 150 characters."}), 400

    # If name changed, check uniqueness
    if name.lower() != series['name'].lower():
        existing = FestModel.get_by_name(name)
        if existing and existing['id'] != series_id:
            return jsonify({"error": "Bad Request", "message": f"A fest named '{name}' already exists."}), 400

    if start_date:
        if not validate_date_str(start_date):
            return jsonify({"error": "Bad Request", "message": "Start date must be in YYYY-MM-DD format."}), 400
    else:
        start_date = None

    if end_date:
        if not validate_date_str(end_date):
            return jsonify({"error": "Bad Request", "message": "End date must be in YYYY-MM-DD format."}), 400
    else:
        end_date = None

    if start_date and end_date:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        if end_d < start_d:
            return jsonify({"error": "Bad Request", "message": "End date must not be earlier than start date."}), 400

    try:
        FestModel.update(
            series_id=series_id,
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date
        )
        updated_series = FestModel.get_by_id(series_id)
        return jsonify({
            "success": True,
            "message": f"Fest '{name}' updated successfully.",
            "series": serialize_data(updated_series),
            "fest": serialize_data(updated_series)
        }), 200
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500

update_management_event_series = update_administrator_fest


@fest_bp.route('/administrator/fests/<int:series_id>', methods=['DELETE'])
@fest_bp.route('/administrator/fest/<int:series_id>', methods=['DELETE'])
@fest_bp.route('/management/event-series/<int:series_id>', methods=['DELETE'])
@require_role('administrator')
def delete_administrator_fest(series_id: int):
    """
    Safely deletes a fest record.
    Protects associated events:
    - If reassign_to is provided in query/body, reassigns all associated events to the target fest.
    - If associated events exist and no reassign_to is specified, returns an error requiring reassignment.
    - If no events are associated, deletes the fest.
    """
    series = FestModel.get_by_id(series_id)
    if not series:
        return jsonify({
            "error": "Not Found",
            "message": f"Fest with ID {series_id} not found."
        }), 404

    data = request.get_json(silent=True) or {}
    reassign_to_raw = request.args.get('reassign_to') or data.get('reassign_to')

    reassign_to_id = None
    if reassign_to_raw is not None and str(reassign_to_raw).strip() != '':
        try:
            reassign_to_id = int(reassign_to_raw)
        except (ValueError, TypeError):
            return jsonify({"error": "Bad Request", "message": "reassign_to must be a valid fest ID."}), 400

    associated_count = FestModel.get_associated_events_count(series_id)
    is_legacy_endpoint = request.path.startswith('/api/management/event-series')

    if associated_count > 0 and reassign_to_id is None and not is_legacy_endpoint:
        return jsonify({
            "error": "Bad Request",
            "message": (
                f"Cannot remove fest '{series['name']}'. It currently has {associated_count} associated event(s). "
                f"Please reassign these events to another fest before removing."
            ),
            "associated_events": associated_count
        }), 400

    try:
        result = FestModel.delete(series_id, reassign_to_series_id=reassign_to_id, allow_unlink=is_legacy_endpoint)
        msg = f"Fest '{series['name']}' deleted successfully."
        if result.get('reassigned_events', 0) > 0:
            msg += f" {result['reassigned_events']} associated event(s) were reassigned to fest ID {reassign_to_id}."
        elif result.get('unlinked_events', 0) > 0:
            msg += f" {result['unlinked_events']} associated event(s) were safely unlinked."

        return jsonify({
            "success": True,
            "message": msg,
            "reassigned_events": result.get('reassigned_events', 0),
            "unlinked_events": result.get('unlinked_events', 0)
        }), 200
    except ValueError as val_err:
        return jsonify({"error": "Bad Request", "message": str(val_err)}), 400
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500

delete_management_event_series = delete_administrator_fest

# Backward compatibility alias
event_series_bp = fest_bp
