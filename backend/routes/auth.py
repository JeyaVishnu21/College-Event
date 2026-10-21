"""
Authentication Routes (Stage 3)
-------------------------------
Provides registration, login, logout, and current user profile endpoints.
Implements secure session-based authentication and role-based access validation.
"""

import re
from flask import Blueprint, request, jsonify, session, g
from config.settings import settings
from middleware.auth import hash_password, require_auth
from models.user import UserModel

auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Registers a new user account.
    - Validates name, email, password, and requested role.
    - Plaintext password is NEVER stored; securely hashed via Werkzeug PBKDF2.
    - Management role requires a valid management_code to prevent privilege escalation.
    - Returns HTTP 201 on success without password hashes.
    """
    data = request.get_json(silent=True) or {}

    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    role = str(data.get('role', 'organizer')).strip().lower()
    if role == 'management':
        role = 'administrator'
    administrator_code = str(data.get('administrator_code', data.get('management_code', ''))).strip()

    # Input validations
    if not name:
        return jsonify({"error": "Bad Request", "message": "Full name is required."}), 400

    if not email or not EMAIL_REGEX.match(email):
        return jsonify({"error": "Bad Request", "message": "A valid email address is required."}), 400

    if not password or len(password) < 6:
        return jsonify({
            "error": "Bad Request", 
            "message": "Password is required and must be at least 6 characters long."
        }), 400

    # Role validation - system supports only Organizer and Administrator accounts
    if role not in ['organizer', 'administrator']:
        return jsonify({
            "error": "Bad Request", 
            "message": "Invalid role. Only Organizer and Administrator accounts are permitted."
        }), 400

    # Privilege Escalation Protection:
    # Ordinary users cannot register as 'administrator' without the secret authorization code
    if role == 'administrator':
        if not administrator_code or administrator_code != settings.ADMINISTRATOR_REGISTRATION_CODE:
            return jsonify({
                "error": "Forbidden",
                "message": "Invalid or missing administrator authorization code. Privilege escalation denied."
            }), 403

    # Check for existing email to prevent duplicates
    existing_user = UserModel.get_by_email(email)
    if existing_user:
        return jsonify({
            "error": "Conflict",
            "message": "An account with this email address already exists. Please log in instead."
        }), 409

    # Securely hash password and create record
    password_hash = hash_password(password)
    try:
        user_id = UserModel.create_user(name, email, password_hash, role)
        created_user = UserModel.get_by_id(user_id)
        safe_user = UserModel.to_safe_dict(created_user)

        return jsonify({
            "message": "Registration successful. You can now log in.",
            "user": safe_user
        }), 201
    except Exception as exc:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Could not complete registration: {str(exc)}"
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticates a user via email and password.
    - Validates credentials against the stored password hash.
    - Enforces two-login system: Only Organizer and Management accounts can log in.
    - Initializes the server-side session.
    - Returns safe user details without any password hashes.
    """
    data = request.get_json(silent=True) or {}

    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))

    if not email or not password:
        return jsonify({
            "error": "Bad Request",
            "message": "Email and password are required."
        }), 400

    # Verify credentials
    safe_user = UserModel.authenticate(email, password)
    if not safe_user:
        return jsonify({
            "error": "Unauthorized",
            "message": "Invalid email or password."
        }), 401

    # Establish session
    session.clear()
    session.permanent = True
    session['user_id'] = safe_user['id']
    session['user_role'] = safe_user['role']

    return jsonify({
        "message": "Login successful.",
        "user": safe_user
    }), 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    Terminates the user's active session.
    Subsequent requests to protected routes will be rejected.
    """
    session.clear()
    return jsonify({
        "message": "Logged out successfully."
    }), 200


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """
    Returns the currently authenticated user's profile.
    Protected route requiring an active session.
    """
    return jsonify({
        "authenticated": True,
        "user": g.current_user
    }), 200


@auth_bp.after_request
def add_auth_no_cache_headers(response):
    """Guarantees authentication endpoints are never cached by browsers or intermediaries."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
