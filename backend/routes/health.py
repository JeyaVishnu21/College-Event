"""
Health Check Route
------------------
Provides GET /api/health to verify that the backend server is running,
and reports connectivity to configuration and database components.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify
from config.db import check_db_status

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint returning application status and environment info.
    """
    db_status = check_db_status()

    payload = {
        "status": "healthy",
        "service": "Crowd Event Management System API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status
    }
    return jsonify(payload), 200
