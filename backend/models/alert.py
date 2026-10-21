"""
Alert Model (Stage 2)
---------------------
Handles database operations for the `alerts` table.
Stores crowd density threshold exceedance alerts for management and organizers.
"""

from typing import Optional, List, Dict, Any
from config.db import get_db_connection


class AlertModel:
    @staticmethod
    def get_by_id(alert_id: int) -> Optional[Dict[str, Any]]:
        """Fetch alert by ID with associated event and venue details."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        a.*,
                        e.event_name,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity
                    FROM alerts a
                    JOIN events e ON a.event_id = e.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    WHERE a.id = %s;
                """, (alert_id,))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_alerts_by_user(user_id: int, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Fetch all alerts targeted to a specific recipient (organizer or administrator)."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                SELECT 
                    a.id,
                    a.event_id,
                    a.user_id,
                    a.crowd_analysis_id,
                    a.detected_count,
                    a.threshold,
                    a.message,
                    a.status,
                    a.created_at,
                    e.event_name,
                    v.name AS venue_name,
                    v.location AS venue_location,
                    v.capacity AS venue_capacity,
                    i.image_path,
                    ca.predicted_count
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN crowd_analyses ca ON a.crowd_analysis_id = ca.id
                LEFT JOIN images i ON ca.image_id = i.id
                WHERE a.user_id = %s
                """
                if unread_only:
                    sql += " AND a.status = 'unread'"
                sql += " ORDER BY a.created_at DESC;"

                cursor.execute(sql, (user_id,))
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_all_alerts(unread_only: bool = False) -> List[Dict[str, Any]]:
        """Fetch all system-wide alerts for administrators."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                SELECT 
                    a.id,
                    a.event_id,
                    a.user_id,
                    a.crowd_analysis_id,
                    a.detected_count,
                    a.threshold,
                    a.message,
                    a.status,
                    a.created_at,
                    e.event_name,
                    v.name AS venue_name,
                    v.location AS venue_location,
                    v.capacity AS venue_capacity,
                    u.name AS recipient_name,
                    u.role AS recipient_role,
                    i.image_path,
                    ca.predicted_count
                FROM alerts a
                JOIN events e ON a.event_id = e.id
                LEFT JOIN venues v ON e.venue_id = v.id
                JOIN users u ON a.user_id = u.id
                LEFT JOIN crowd_analyses ca ON a.crowd_analysis_id = ca.id
                LEFT JOIN images i ON ca.image_id = i.id
                """
                if unread_only:
                    sql += " WHERE a.status = 'unread'"
                sql += " ORDER BY a.created_at DESC;"

                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """Fetch count of unread alerts for a specific user."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM alerts WHERE user_id = %s AND status = 'unread';",
                    (user_id,)
                )
                res = cursor.fetchone()
                return int(res.get('count') or 0) if res else 0
        finally:
            conn.close()

    @staticmethod
    def get_all_unread_count() -> int:
        """Fetch total count of unread alerts across the system for administrator overview."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM alerts WHERE status = 'unread';")
                res = cursor.fetchone()
                return int(res.get('count') or 0) if res else 0
        finally:
            conn.close()

    @staticmethod
    def get_alerts_by_event(event_id: int) -> List[Dict[str, Any]]:
        """Fetch all alerts generated during a specific event."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.*, u.name AS recipient_name, u.role AS recipient_role
                    FROM alerts a
                    JOIN users u ON a.user_id = u.id
                    WHERE a.event_id = %s
                    ORDER BY a.created_at DESC;
                    """,
                    (event_id,)
                )
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def create_alert(
        event_id: int,
        user_id: int,
        detected_count: int,
        threshold: int,
        message: str,
        crowd_analysis_id: Optional[int] = None
    ) -> int:
        """Create a new threshold alert record."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO alerts (
                        event_id, user_id, crowd_analysis_id,
                        detected_count, threshold, message, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'unread');
                    """,
                    (event_id, user_id, crowd_analysis_id, detected_count, threshold, message.strip())
                )
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def mark_as_read(alert_id: int, user_id: Optional[int] = None) -> bool:
        """Mark an alert status as read."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if user_id is not None:
                    cursor.execute(
                        "UPDATE alerts SET status = 'read' WHERE id = %s AND user_id = %s;",
                        (alert_id, user_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE alerts SET status = 'read' WHERE id = %s;",
                        (alert_id,)
                    )
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def mark_all_as_read(user_id: int) -> int:
        """Mark all unread alerts for a user as read."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE alerts SET status = 'read' WHERE user_id = %s AND status = 'unread';",
                    (user_id,)
                )
                return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def mark_all_system_as_read() -> int:
        """Mark all unread alerts across the system as read (for administrators)."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE alerts SET status = 'read' WHERE status = 'unread';")
                return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def evaluate_and_create_alerts(
        event_id: int,
        crowd_analysis_id: int,
        predicted_count: int
    ) -> List[int]:
        """
        Evaluates crowd headcount against the assigned venue capacity.
        Threshold rule: threshold = max(0, venue.capacity - 50).
        If predicted_count >= threshold:
            Dispatches automated alerts to the event organizer and all campus administrators.
            - If predicted_count >= capacity: Critical Capacity Breach.
            - If predicted_count >= threshold and < capacity: High Crowd Warning.
        Returns the list of created alert IDs.
        """
        from models.event import EventModel
        from models.venue import VenueModel
        from models.user import UserModel

        event = EventModel.get_by_id(event_id)
        if not event:
            return []

        venue_capacity = event.get('venue_capacity')
        venue_name = event.get('venue_name')
        if (venue_capacity is None or venue_capacity <= 0) and event.get('venue_id'):
            v = VenueModel.get_by_id(event.get('venue_id'))
            if v:
                venue_capacity = v.get('capacity')
                if not venue_name:
                    venue_name = v.get('name')

        capacity = int(venue_capacity or 0)
        if capacity <= 0:
            return []

        threshold = max(0, capacity - 50)
        if predicted_count < threshold:
            return []

        event_name = event.get('event_name') or 'Event'
        venue_display = venue_name or 'Assigned Venue'

        if predicted_count >= capacity:
            message = (
                f"CRITICAL BREACH: Detected crowd headcount ({predicted_count}) exceeds "
                f"venue capacity ({capacity}) for '{event_name}' at {venue_display}."
            )
        else:
            message = (
                f"HIGH CROWD WARNING: Detected crowd headcount ({predicted_count}) has reached or exceeded "
                f"warning threshold ({threshold}) for '{event_name}' at {venue_display} (Capacity: {capacity})."
            )

        recipient_ids = set()
        if event.get('organizer_id'):
            recipient_ids.add(event['organizer_id'])

        try:
            admins = list(UserModel.get_by_role('administrator') or []) + list(UserModel.get_by_role('management') or [])
            for adm in admins:
                recipient_ids.add(adm['id'])
        except Exception as e:
            pass

        created_ids = []
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Verify crowd_analysis_id exists if provided to prevent FK constraint error
                valid_ca_id = None
                if crowd_analysis_id is not None:
                    cursor.execute("SELECT id FROM crowd_analyses WHERE id = %s;", (crowd_analysis_id,))
                    if cursor.fetchone():
                        valid_ca_id = crowd_analysis_id

                for uid in recipient_ids:
                    if valid_ca_id is not None:
                        cursor.execute(
                            "SELECT id FROM alerts WHERE crowd_analysis_id = %s AND user_id = %s LIMIT 1;",
                            (valid_ca_id, uid)
                        )
                        existing = cursor.fetchone()
                    else:
                        existing = None

                    if not existing:
                        cursor.execute(
                            """
                            INSERT INTO alerts (
                                event_id, user_id, crowd_analysis_id,
                                detected_count, threshold, message, status
                            ) VALUES (%s, %s, %s, %s, %s, %s, 'unread');
                            """,
                            (event_id, uid, valid_ca_id, predicted_count, threshold, message.strip())
                        )
                        created_ids.append(cursor.lastrowid)
            return created_ids
        finally:
            conn.close()

