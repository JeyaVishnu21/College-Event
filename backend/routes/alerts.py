"""
Alert Routes
------------
Provides RESTful endpoints for viewing, managing, and acknowledging real-time crowd safety alerts.
Allows event organizers to view alerts for their events and administrators to view system-wide alerts.
"""

import logging
from datetime import timedelta
from typing import Any
from flask import Blueprint, jsonify, request, g

from middleware.auth import require_auth
from models.alert import AlertModel
from models.event import EventModel

logger = logging.getLogger(__name__)
alerts_bp = Blueprint('alerts', __name__)


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


@alerts_bp.route('/alerts', methods=['GET'])
@require_auth
def get_alerts():
    """
    Retrieve real-time crowd density alerts.
    - Administrators/Management receive all system-wide alerts.
    - Organizers receive alerts targeted to them or their events.
    Supports ?unread_only=true and ?event_id=<id> filters.
    """
    user = g.current_user
    user_role = user.get('role')
    unread_only = request.args.get('unread_only', '').lower() in ('true', '1')
    event_id_raw = request.args.get('event_id')

    event_id = None
    if event_id_raw:
        try:
            event_id = int(event_id_raw)
        except ValueError:
            return jsonify({
                "error": "Bad Request",
                "message": "Invalid event_id query parameter."
            }), 400

    effective_admins = {'administrator', 'management'}
    scope = request.args.get('scope', 'user')

    if user_role in effective_admins and scope == 'all':
        alerts = AlertModel.get_all_alerts(unread_only=unread_only)
        unread_count = AlertModel.get_all_unread_count()
    elif user_role in effective_admins or user_role == 'organizer':
        alerts = AlertModel.get_alerts_by_user(user['id'], unread_only=unread_only)
        unread_count = AlertModel.get_unread_count(user['id'])
    else:
        return jsonify({
            "error": "Forbidden",
            "message": "Access denied. Role not permitted to view safety alerts."
        }), 403

    if event_id is not None:
        alerts = [a for a in alerts if a.get('event_id') == event_id]

    return jsonify({
        "success": True,
        "unread_count": unread_count,
        "total_count": len(alerts),
        "alerts": serialize_data(alerts)
    }), 200


@alerts_bp.route('/alerts/unread-count', methods=['GET'])
@require_auth
def get_unread_alerts_count():
    """Retrieve count of unread crowd safety alerts for badge indicators."""
    user = g.current_user
    user_role = user.get('role')
    effective_admins = {'administrator', 'management'}

    if user_role in effective_admins:
        count = AlertModel.get_all_unread_count()
    elif user_role == 'organizer':
        count = AlertModel.get_unread_count(user['id'])
    else:
        count = 0

    return jsonify({
        "success": True,
        "unread_count": count
    }), 200


@alerts_bp.route('/alerts/<int:alert_id>/read', methods=['PATCH'])
@require_auth
def mark_alert_read(alert_id: int):
    """Mark a specific alert as read."""
    user = g.current_user
    user_role = user.get('role')
    effective_admins = {'administrator', 'management'}

    alert = AlertModel.get_by_id(alert_id)
    if not alert:
        return jsonify({
            "error": "Not Found",
            "message": "Alert not found."
        }), 404

    # Authorization
    if user_role not in effective_admins and alert.get('user_id') != user['id']:
        return jsonify({
            "error": "Forbidden",
            "message": "Access denied. You can only acknowledge alerts targeted to you."
        }), 403

    if user_role in effective_admins:
        AlertModel.mark_as_read(alert_id)
    else:
        AlertModel.mark_as_read(alert_id, user_id=user['id'])

    return jsonify({
        "success": True,
        "message": "Alert marked as read.",
        "alert_id": alert_id
    }), 200


@alerts_bp.route('/alerts/mark-all-read', methods=['POST'])
@require_auth
def mark_all_alerts_read():
    """Mark all unread alerts as read for the current user/context."""
    user = g.current_user
    user_role = user.get('role')
    effective_admins = {'administrator', 'management'}

    if user_role in effective_admins:
        count = AlertModel.mark_all_system_as_read()
    elif user_role == 'organizer':
        count = AlertModel.mark_all_as_read(user['id'])
    else:
        return jsonify({
            "error": "Forbidden",
            "message": "Access denied."
        }), 403

    return jsonify({
        "success": True,
        "message": f"{count} alerts marked as read.",
        "updated_count": count
    }), 200
