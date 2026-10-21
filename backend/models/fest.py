"""
Fest Model
----------
Handles database operations for the `fest` table.
Supports fest discovery, grouping, and retrieval of grouped events.
"""

from datetime import date
from typing import Optional, List, Dict, Any
from config.db import get_db_connection


class FestModel:
    @staticmethod
    def compute_status(start_date_val: Any, end_date_val: Any) -> Dict[str, str]:
        """
        Calculate logical status (upcoming, ongoing, completed) dynamically
        using the current date against start_date and end_date.
        """
        today = date.today()

        s_date = start_date_val
        if isinstance(s_date, str):
            try:
                s_date = date.fromisoformat(s_date.strip())
            except Exception:
                pass

        e_date = end_date_val
        if isinstance(e_date, str):
            try:
                e_date = date.fromisoformat(e_date.strip())
            except Exception:
                pass

        if e_date and today > e_date:
            return {"status": "completed", "computed_status": "Completed"}
        if s_date and today < s_date:
            return {"status": "upcoming", "computed_status": "Upcoming"}
        return {"status": "ongoing", "computed_status": "Ongoing"}

    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """Retrieve all fests ordered chronologically with active event counts (Public view)."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        s.id,
                        s.name,
                        s.description,
                        s.start_date,
                        s.end_date,
                        s.created_at,
                        s.updated_at,
                        COUNT(e.id) AS event_count
                    FROM fest s
                    LEFT JOIN events e ON s.id = e.series_id 
                        AND e.status IN ('approved', 'completed')
                    GROUP BY s.id, s.name, s.description, s.start_date, s.end_date, s.created_at, s.updated_at
                    ORDER BY s.start_date DESC, s.id DESC;
                """)
                rows = cursor.fetchall()
                for r in rows:
                    st = FestModel.compute_status(r.get('start_date'), r.get('end_date'))
                    r['status'] = st['status']
                    r['computed_status'] = st['computed_status']
                return rows
        finally:
            conn.close()

    @staticmethod
    def get_by_name(name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a fest by exact or case-insensitive name match."""
        if not name:
            return None
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM fest WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s)) LIMIT 1;",
                    (name.strip(),)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_administrator_list() -> List[Dict[str, Any]]:
        """
        Retrieve all fests for Administrator overview.
        Includes total associated events count, approved events count, and computed logical status.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        s.id,
                        s.name,
                        s.description,
                        s.start_date,
                        s.end_date,
                        s.created_at,
                        s.updated_at,
                        COUNT(e.id) AS event_count,
                        COUNT(CASE WHEN e.status = 'approved' THEN 1 END) AS approved_event_count
                    FROM fest s
                    LEFT JOIN events e ON s.id = e.series_id
                    GROUP BY s.id, s.name, s.description, s.start_date, s.end_date, s.created_at, s.updated_at
                    ORDER BY s.start_date DESC, s.id DESC;
                """)
                rows = cursor.fetchall()
                for r in rows:
                    st = FestModel.compute_status(r.get('start_date'), r.get('end_date'))
                    r['status'] = st['status']
                    r['computed_status'] = st['computed_status']
                    r['event_count'] = int(r.get('event_count') or 0)
                    r['approved_event_count'] = int(r.get('approved_event_count') or 0)
                return rows
        finally:
            conn.close()

    # Backward compatibility alias
    get_management_list = get_administrator_list

    @staticmethod
    def get_by_id(series_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a single fest by ID with associated event count and computed status."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        s.id,
                        s.name,
                        s.description,
                        s.start_date,
                        s.end_date,
                        s.created_at,
                        s.updated_at,
                        (SELECT COUNT(*) FROM events e WHERE e.series_id = s.id) AS event_count
                    FROM fest s
                    WHERE s.id = %s;
                """, (series_id,))
                row = cursor.fetchone()
                if row:
                    st = FestModel.compute_status(row.get('start_date'), row.get('end_date'))
                    row['status'] = st['status']
                    row['computed_status'] = st['computed_status']
                return row
        finally:
            conn.close()

    @staticmethod
    def get_series_with_events(series_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a fest along with its associated public (approved/completed) events."""
        series = FestModel.get_by_id(series_id)
        if not series:
            return None

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        e.id,
                        e.event_name,
                        e.description,
                        COALESCE(e.category, 'General') AS category,
                        e.status,
                        COALESCE(e.approved_date, e.requested_date) AS event_date,
                        COALESCE(e.approved_start_time, e.requested_start_time) AS start_time,
                        COALESCE(e.approved_end_time, e.requested_end_time) AS end_time,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity,
                        max_ca.max_crowd_count
                    FROM events e
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN (
                        SELECT img.event_id, MAX(ca.predicted_count) AS max_crowd_count
                        FROM images img
                        JOIN crowd_analyses ca ON img.id = ca.image_id
                        WHERE ca.processing_status = 'completed'
                        GROUP BY img.event_id
                    ) max_ca ON e.id = max_ca.event_id
                    WHERE e.series_id = %s
                      AND e.status IN ('approved', 'completed')
                    ORDER BY event_date ASC, start_time ASC;
                """, (series_id,))
                events = cursor.fetchall()
                series['events'] = events
                series['total_events'] = len(events)
                return series
        finally:
            conn.close()

    # Alias for fest terminology
    get_fest_with_events = get_series_with_events

    @staticmethod
    def get_fest_approved_events(series_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve all approved events specifically belonging to the given fest.
        Includes organizer credentials, allocated venue details, schedule, and expected participants.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        e.id,
                        e.organizer_id,
                        e.event_name,
                        e.description,
                        COALESCE(e.category, 'General') AS category,
                        e.status,
                        e.requested_date,
                        e.requested_start_time,
                        e.requested_end_time,
                        e.approved_date,
                        e.approved_start_time,
                        e.approved_end_time,
                        COALESCE(e.approved_date, e.requested_date) AS event_date,
                        COALESCE(e.approved_start_time, e.requested_start_time) AS start_time,
                        COALESCE(e.approved_end_time, e.requested_end_time) AS end_time,
                        e.venue_id,
                        e.series_id,
                        e.expected_participants,
                        u.name AS organizer_name,
                        u.email AS organizer_email,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity,
                        v.status AS venue_status
                    FROM events e
                    JOIN users u ON e.organizer_id = u.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    WHERE e.series_id = %s
                      AND e.status = 'approved'
                    ORDER BY event_date ASC, start_time ASC;
                """, (series_id,))
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_unassigned_approved_events() -> List[Dict[str, Any]]:
        """
        Retrieve approved events that currently have no fest assigned (series_id IS NULL).
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        e.id,
                        e.organizer_id,
                        e.event_name,
                        e.description,
                        COALESCE(e.category, 'General') AS category,
                        e.status,
                        e.requested_date,
                        e.requested_start_time,
                        e.requested_end_time,
                        e.approved_date,
                        e.approved_start_time,
                        e.approved_end_time,
                        COALESCE(e.approved_date, e.requested_date) AS event_date,
                        COALESCE(e.approved_start_time, e.requested_start_time) AS start_time,
                        COALESCE(e.approved_end_time, e.requested_end_time) AS end_time,
                        e.venue_id,
                        e.series_id,
                        e.expected_participants,
                        u.name AS organizer_name,
                        u.email AS organizer_email,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity
                    FROM events e
                    JOIN users u ON e.organizer_id = u.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    WHERE e.series_id IS NULL
                      AND e.status = 'approved'
                    ORDER BY event_date ASC, start_time ASC;
                """)
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def assign_event_to_fest(event_id: int, series_id: Optional[int]) -> bool:
        """Safely associates an event with a fest (or unlinks if series_id is None)."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE events SET series_id = %s WHERE id = %s;",
                    (series_id, event_id)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def reassign_events(source_series_id: int, target_series_id: int) -> int:
        """Reassign all events from source fest to target fest."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE events SET series_id = %s WHERE series_id = %s;",
                    (target_series_id, source_series_id)
                )
                return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def create(name: str, description: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> int:
        """Create a new fest record with optional description and dates."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO fest (name, description, start_date, end_date)
                    VALUES (%s, %s, %s, %s);
                """, (
                    name.strip(),
                    description.strip() if description and description.strip() else None,
                    start_date.strip() if start_date and start_date.strip() else None,
                    end_date.strip() if end_date and end_date.strip() else None
                ))
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def update(series_id: int, name: str, description: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> bool:
        """Update an existing fest record with optional description and dates."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE fest
                    SET name = %s,
                        description = %s,
                        start_date = %s,
                        end_date = %s
                    WHERE id = %s;
                """, (
                    name.strip(),
                    description.strip() if description and description.strip() else None,
                    start_date.strip() if start_date and start_date.strip() else None,
                    end_date.strip() if end_date and end_date.strip() else None,
                    series_id
                ))
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def delete(series_id: int, reassign_to_series_id: Optional[int] = None, allow_unlink: bool = False) -> Dict[str, Any]:
        """
        Safely deletes a fest record.
        Protects events associated with the fest:
        - If reassign_to_series_id is specified, moves all events to the target fest.
        - If allow_unlink is True, unlinks events by setting series_id = NULL.
        - If not specified and there are associated events, raises ValueError to prevent accidental loss.
        - If no events are associated, safely removes the fest.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 1. Count associated events
                cursor.execute("SELECT COUNT(*) AS count FROM events WHERE series_id = %s;", (series_id,))
                count_res = cursor.fetchone()
                linked_count = count_res['count'] if count_res else 0

                # 2. Handle reassignment, unlinking, or block
                if linked_count > 0:
                    if reassign_to_series_id is not None:
                        # Verify target fest exists and is different
                        if int(reassign_to_series_id) == int(series_id):
                            raise ValueError("Cannot reassign events to the fest being deleted.")
                        cursor.execute("SELECT id, name FROM fest WHERE id = %s;", (reassign_to_series_id,))
                        target_fest = cursor.fetchone()
                        if not target_fest:
                            raise ValueError(f"Target fest ID {reassign_to_series_id} for reassignment not found.")
                        cursor.execute(
                            "UPDATE events SET series_id = %s WHERE series_id = %s;",
                            (reassign_to_series_id, series_id)
                        )
                    elif allow_unlink:
                        cursor.execute("UPDATE events SET series_id = NULL WHERE series_id = %s;", (series_id,))
                    else:
                        raise ValueError(
                            f"Fest has {linked_count} associated event(s). Please reassign them before deletion."
                        )

                # 3. Delete the fest record
                cursor.execute("DELETE FROM fest WHERE id = %s;", (series_id,))
                deleted = cursor.rowcount > 0

                return {
                    "deleted": deleted,
                    "reassigned_events": linked_count if reassign_to_series_id else 0,
                    "unlinked_events": linked_count if (linked_count > 0 and reassign_to_series_id is None and allow_unlink) else 0,
                    "reassigned_to": reassign_to_series_id
                }
        finally:
            conn.close()

    @staticmethod
    def get_associated_events_count(series_id: int) -> int:
        """Count how many events currently reference this fest ID."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM events WHERE series_id = %s;", (series_id,))
                res = cursor.fetchone()
                return res['count'] if res else 0
        finally:
            conn.close()


# Backward compatibility alias
EventSeriesModel = FestModel
