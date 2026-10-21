"""
Protected Test Routes (Stage 3)
-------------------------------
Provides sample protected endpoints to verify role-based authorization:
- /api/organizer/dashboard-data (requires 'organizer')
- /api/management/dashboard-data (requires 'management')
"""

from flask import Blueprint, jsonify, g
from middleware.auth import require_role

protected_bp = Blueprint('protected', __name__)


@protected_bp.route('/organizer/dashboard-data', methods=['GET'])
@require_role('organizer')
def organizer_dashboard_data():
    """
    Protected endpoint accessible ONLY to users with the 'organizer' role.
    Management and unauthenticated users are denied.
    """
    return jsonify({
        "status": "success",
        "message": f"Welcome to Organizer Portal, {g.current_user['name']}!",
        "role": g.current_user['role'],
        "user_id": g.current_user['id'],
        "permissions": [
            "create_event_requests",
            "view_own_events",
            "upload_event_images",
            "view_own_event_crowd_analyses"
        ]
    }), 200


@protected_bp.route('/administrator/dashboard-data', methods=['GET'])
@protected_bp.route('/management/dashboard-data', methods=['GET'])
@require_role('administrator')
def administrator_dashboard_data():
    """
    Protected endpoint accessible ONLY to users with the 'administrator' role.
    Organizers and unauthenticated users are denied.
    """
    return jsonify({
        "status": "success",
        "message": f"Welcome to Administrator Console, {g.current_user['name']}!",
        "role": g.current_user['role'],
        "user_id": g.current_user['id'],
        "permissions": [
            "manage_venues",
            "review_event_requests",
            "approve_reject_events",
            "allocate_schedules",
            "monitor_crowd_alerts",
            "view_reports"
        ]
    }), 200


management_dashboard_data = administrator_dashboard_data
