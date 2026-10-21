"""
Venue Routes (Stage 4)
----------------------
Handles venue operations and querying.
All modification endpoints require the 'administrator' role.
Venue listings are accessible to authenticated users to support organizer preferences.
"""

from flask import Blueprint, request, jsonify
from middleware.auth import require_auth, require_role
from models.venue import VenueModel

venues_bp = Blueprint('venues', __name__)


@venues_bp.route('', methods=['GET'])
@require_auth
def get_all_venues():
    """Retrieve all college venues."""
    venues = VenueModel.get_all()
    return jsonify({"venues": venues}), 200


@venues_bp.route('/<int:venue_id>', methods=['GET'])
@require_auth
def get_venue(venue_id: int):
    """Retrieve details for a single venue."""
    venue = VenueModel.get_by_id(venue_id)
    if not venue:
        return jsonify({"error": "Not Found", "message": f"Venue with ID {venue_id} not found."}), 404
    return jsonify({"venue": venue}), 200


@venues_bp.route('', methods=['POST'])
@require_role('administrator')
def create_venue():
    """
    Create a new venue.
    Administrator authorization strictly required.
    """
    data = request.get_json(silent=True) or {}

    name = str(data.get('name', '')).strip()
    location = str(data.get('location', '')).strip()
    capacity_raw = data.get('capacity', 0)
    status = str(data.get('status', 'available')).strip().lower()

    if not name:
        return jsonify({"error": "Bad Request", "message": "Venue name is required."}), 400

    if not location:
        return jsonify({"error": "Bad Request", "message": "Venue location is required."}), 400

    try:
        capacity = int(capacity_raw)
        if capacity < 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Bad Request", "message": "Capacity must be a non-negative integer."}), 400

    if status not in VenueModel.STATUSES:
        return jsonify({
            "error": "Bad Request", 
            "message": f"Invalid status '{status}'. Must be one of {VenueModel.STATUSES}."
        }), 400

    try:
        venue_id = VenueModel.create_venue(name, location, capacity, status)
        created_venue = VenueModel.get_by_id(venue_id)
        return jsonify({
            "message": "Venue created successfully.",
            "venue": created_venue
        }), 201
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500


@venues_bp.route('/<int:venue_id>', methods=['PUT'])
@require_role('administrator')
def update_venue(venue_id: int):
    """
    Update venue details and status.
    Administrator authorization strictly required.
    """
    existing = VenueModel.get_by_id(venue_id)
    if not existing:
        return jsonify({"error": "Not Found", "message": f"Venue with ID {venue_id} not found."}), 404

    data = request.get_json(silent=True) or {}

    name = str(data.get('name', existing['name'])).strip()
    location = str(data.get('location', existing['location'])).strip()
    capacity_raw = data.get('capacity', existing['capacity'])
    status = str(data.get('status', existing['status'])).strip().lower()

    if not name or not location:
        return jsonify({"error": "Bad Request", "message": "Venue name and location cannot be empty."}), 400

    try:
        capacity = int(capacity_raw)
        if capacity < 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Bad Request", "message": "Capacity must be a non-negative integer."}), 400

    if status not in VenueModel.STATUSES:
        return jsonify({
            "error": "Bad Request", 
            "message": f"Invalid status '{status}'. Must be one of {VenueModel.STATUSES}."
        }), 400

    try:
        VenueModel.update_venue(venue_id, name, location, capacity, status)
        updated_venue = VenueModel.get_by_id(venue_id)
        return jsonify({
            "message": "Venue updated successfully.",
            "venue": updated_venue
        }), 200
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500


@venues_bp.route('/<int:venue_id>/status', methods=['PATCH'])
@require_role('administrator')
def update_venue_status(venue_id: int):
    """
    Quick availability toggle for a venue.
    Administrator authorization strictly required.
    """
    existing = VenueModel.get_by_id(venue_id)
    if not existing:
        return jsonify({"error": "Not Found", "message": f"Venue with ID {venue_id} not found."}), 404

    data = request.get_json(silent=True) or {}
    status = str(data.get('status', '')).strip().lower()

    if status not in VenueModel.STATUSES:
        return jsonify({
            "error": "Bad Request", 
            "message": f"Invalid status '{status}'. Allowed statuses: {VenueModel.STATUSES}."
        }), 400

    VenueModel.update_status(venue_id, status)
    updated_venue = VenueModel.get_by_id(venue_id)
    return jsonify({
        "message": f"Venue availability updated to '{status}'.",
        "venue": updated_venue
    }), 200


@venues_bp.route('/<int:venue_id>', methods=['DELETE'])
@require_role('administrator')
def delete_venue(venue_id: int):
    """
    Safely delete a venue.
    Rejects deletion if any events are associated with the venue to prevent orphaned records.
    """
    existing = VenueModel.get_by_id(venue_id)
    if not existing:
        return jsonify({"error": "Not Found", "message": f"Venue with ID {venue_id} not found."}), 404

    if VenueModel.has_associated_events(venue_id):
        return jsonify({
            "error": "Bad Request",
            "message": "Cannot delete venue: it is associated with existing events. Please mark it as 'unavailable' instead."
        }), 400

    try:
        VenueModel.delete_venue(venue_id)
        return jsonify({
            "message": f"Venue '{existing['name']}' deleted successfully."
        }), 200
    except Exception as exc:
        return jsonify({"error": "Internal Server Error", "message": str(exc)}), 500
