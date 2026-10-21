"""
User Model (Stage 2 & 3)
------------------------
Handles database operations for the `users` table.
Supports the distinct roles: 'administrator' and 'organizer'.
Includes safe dictionary serialization and password verification methods.
"""

from typing import Optional, List, Dict, Any
from werkzeug.security import check_password_hash
from config.db import get_db_connection


class UserModel:
    ROLES = ['administrator', 'management', 'organizer']

    @staticmethod
    def to_safe_dict(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Strips sensitive fields like password_hash from the user dict.
        Ensures password hashes are never returned to frontend or external callers.
        """
        if not user:
            return None
        safe_user = dict(user)
        safe_user.pop('password_hash', None)
        return safe_user

    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single user by their primary key."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, email, role, created_at, updated_at FROM users WHERE id = %s;",
                    (user_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        """Fetch a single user by their unique email, including password_hash for authentication."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, email, password_hash, role, created_at, updated_at FROM users WHERE email = %s;",
                    (email.lower().strip(),)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_by_role(role: str) -> List[Dict[str, Any]]:
        """Fetch all users assigned to a specific role."""
        if role not in UserModel.ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of {UserModel.ROLES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, email, role, created_at FROM users WHERE role = %s ORDER BY id ASC;",
                    (role,)
                )
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def create_user(name: str, email: str, password_hash: str, role: str) -> int:
        """Insert a new user record with a pre-hashed password and return the new ID."""
        if role not in UserModel.ROLES:
            raise ValueError(f"Invalid role: {role}. Allowed roles: {UserModel.ROLES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (name.strip(), email.lower().strip(), password_hash, role)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def authenticate(email: str, raw_password: str) -> Optional[Dict[str, Any]]:
        """
        Validates user credentials against the stored password hash.
        Returns a sanitized user dictionary on success, or None on failure.
        """
        user = UserModel.get_by_email(email)
        if not user or not user.get('password_hash'):
            return None

        if check_password_hash(user['password_hash'], raw_password):
            return UserModel.to_safe_dict(user)
        return None
