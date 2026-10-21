"""
Venue Model (Stage 2 & 4)
-------------------------
Handles database operations for the `venues` table.
Supports venue CRUD operations, availability management,
scheduling conflict detection, and student crowd-level queries.
"""

from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
from config.db import get_db_connection


class VenueModel:
    STATUSES = ['available', 'unavailable']

    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """Retrieve all college venues."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, location, capacity, status, created_at, updated_at FROM venues ORDER BY id ASC;"
                )
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_venue_statistics() -> Dict[str, int]:
        """
        Calculates venue counts: total, available, and unavailable.
        """
        sql = """
        SELECT 
            COUNT(*) AS total_venues,
            SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) AS available_venues,
            SUM(CASE WHEN status = 'unavailable' THEN 1 ELSE 0 END) AS unavailable_venues
        FROM venues;
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                row = cursor.fetchone() or {}
                return {
                    "total_venues": int(row.get("total_venues") or 0),
                    "available_venues": int(row.get("available_venues") or 0),
                    "unavailable_venues": int(row.get("unavailable_venues") or 0),
                }
        finally:
            conn.close()

    @staticmethod
    def get_by_id(venue_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific venue by ID."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, location, capacity, status, created_at, updated_at FROM venues WHERE id = %s;",
                    (venue_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def create_venue(name: str, location: str, capacity: int, status: str = 'available') -> int:
        """Create a new college venue record."""
        if status not in VenueModel.STATUSES:
            raise ValueError(f"Invalid status: {status}. Allowed: {VenueModel.STATUSES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO venues (name, location, capacity, status)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (name.strip(), location.strip(), int(capacity), status)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def update_venue(venue_id: int, name: str, location: str, capacity: int, status: str) -> bool:
        """Update existing venue details and availability status."""
        if status not in VenueModel.STATUSES:
            raise ValueError(f"Invalid status: {status}. Allowed: {VenueModel.STATUSES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE venues
                    SET name = %s, location = %s, capacity = %s, status = %s
                    WHERE id = %s;
                    """,
                    (name.strip(), location.strip(), int(capacity), status, venue_id)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def update_status(venue_id: int, status: str) -> bool:
        """Quickly toggle availability status for a venue."""
        if status not in VenueModel.STATUSES:
            raise ValueError(f"Invalid status: {status}. Allowed: {VenueModel.STATUSES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE venues SET status = %s WHERE id = %s;",
                    (status, venue_id)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def has_associated_events(venue_id: int) -> bool:
        """Check if any events reference this venue."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM events WHERE venue_id = %s;", (venue_id,))
                result = cursor.fetchone()
                return (result.get('count', 0) if result else 0) > 0
        finally:
            conn.close()

    @staticmethod
    def delete_venue(venue_id: int) -> bool:
        """
        Safely deletes a venue.
        Rejects deletion if any events are associated with the venue to prevent orphaned schedules.
        """
        if VenueModel.has_associated_events(venue_id):
            raise ValueError("Cannot delete venue: it is associated with one or more scheduled events.")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM venues WHERE id = %s;", (venue_id,))
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def check_conflict(
        venue_id: int, 
        date_str: str, 
        start_time_str: str, 
        end_time_str: str, 
        exclude_event_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Checks for scheduling conflicts for an approved event at the specified venue.
        Overlapping interval logic:
          Existing event overlaps with requested time if:
          approved_start_time < new_end_time AND approved_end_time > new_start_time
        Returns the conflicting event record if conflict exists, or None.
        """
        sql = """
        SELECT id, event_name, approved_date, approved_start_time, approved_end_time
        FROM events
        WHERE venue_id = %s
          AND status = 'approved'
          AND approved_date = %s
          AND approved_start_time < %s
          AND approved_end_time > %s
        """
        params = [venue_id, date_str, end_time_str, start_time_str]

        if exclude_event_id is not None:
            sql += " AND id != %s"
            params.append(exclude_event_id)

        sql += " LIMIT 1;"

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_venues_with_current_crowd(
        ref_date: Optional[date] = None, 
        ref_time: Optional[time] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all venues along with their CURRENTLY ACTIVE event and
        the latest estimated crowd count derived from crowd_analyses records.
        """
        date_param = ref_date.isoformat() if ref_date else None
        time_param = ref_time.strftime("%H:%M:%S") if ref_time else None

        query = """
        SELECT 
            v.id AS venue_id,
            v.name AS venue_name,
            v.location AS venue_location,
            v.capacity AS venue_capacity,
            v.status AS venue_status,
            e.id AS current_event_id,
            e.event_name AS current_event_name,
            e.approved_date,
            e.approved_start_time,
            e.approved_end_time,
            latest_ca.predicted_count AS current_crowd_count,
            latest_ca.analysis_timestamp AS last_analyzed_at
        FROM venues v
        LEFT JOIN events e ON v.id = e.venue_id 
            AND e.status = 'approved'
            AND e.approved_date = COALESCE(%s, CURRENT_DATE())
            AND COALESCE(%s, CURRENT_TIME()) BETWEEN e.approved_start_time AND e.approved_end_time
        LEFT JOIN (
            SELECT 
                img.event_id, 
                ca.predicted_count, 
                ca.analysis_timestamp
            FROM crowd_analyses ca
            JOIN images img ON ca.image_id = img.id
            WHERE (img.event_id, ca.analysis_timestamp) IN (
                SELECT img_sub.event_id, MAX(ca_sub.analysis_timestamp)
                FROM crowd_analyses ca_sub
                JOIN images img_sub ON ca_sub.image_id = img_sub.id
                GROUP BY img_sub.event_id
            )
        ) latest_ca ON e.id = latest_ca.event_id
        ORDER BY v.id ASC;
        """

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, (date_param, time_param))
                return cursor.fetchall()
        finally:
            conn.close()
