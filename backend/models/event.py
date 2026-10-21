"""
Event Model (Stage 2 & 4)
-------------------------
Handles database operations for the `events` table.
Maintains strict separation between organizer requested schedule and
management final allocated schedule. Supports review, approval/rejection,
and student visibility queries.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime, time, timedelta
from config.db import get_db_connection


class EventModel:
    STATUSES = ['pending', 'approved', 'rejected', 'completed', 'cancelled']

    @classmethod
    def _get_current_time(cls) -> datetime:
        """Returns the current server datetime with timezone."""
        return datetime.now().astimezone()

    @staticmethod
    def is_event_happening(event: Dict[str, Any], current_datetime: Optional[Any] = None) -> Tuple[bool, str]:
        """
        Evaluates whether an event is actively happening according to management's final approved schedule.
        Returns (is_happening: bool, reason_message: str).

        Strict Requirements:
          1. Status must be 'approved'.
          2. Final management-assigned schedule (approved_date, approved_start_time, approved_end_time) exists and is valid.
          3. Final scheduled date is today (server local date).
          4. Current server time satisfies start_time <= current_time < end_time.
          5. Denies uploads before start time, at or after end time, on other dates, for unapproved events,
             and for missing/invalid schedules.
        """
        if not event:
            return False, "Event record not found."

        raw_status = (event.get('status') or '').lower()
        if raw_status != 'approved':
            status_desc = event.get('status') or 'unapproved'
            return False, f"Photo upload is blocked: event status is '{status_desc}'. Photos can only be uploaded for approved events."

        approved_date_raw = event.get('approved_date')
        start_time_raw = event.get('approved_start_time')
        end_time_raw = event.get('approved_end_time')

        if approved_date_raw is None or start_time_raw is None or end_time_raw is None:
            return False, "Photo upload is blocked: event does not have a confirmed management-approved schedule."

        if isinstance(approved_date_raw, str) and not approved_date_raw.strip():
            return False, "Photo upload is blocked: event does not have a confirmed management-approved schedule."
        if isinstance(start_time_raw, str) and not start_time_raw.strip():
            return False, "Photo upload is blocked: event does not have a confirmed management-approved schedule."
        if isinstance(end_time_raw, str) and not end_time_raw.strip():
            return False, "Photo upload is blocked: event does not have a confirmed management-approved schedule."

        # Server time in local timezone
        if current_datetime is not None:
            now_dt = current_datetime
        else:
            now_dt = EventModel._get_current_time()

        today_date = now_dt.date()
        current_time = now_dt.time()

        # Parse approved_date
        if isinstance(approved_date_raw, str):
            try:
                approved_date = datetime.strptime(approved_date_raw.split('T')[0], '%Y-%m-%d').date()
            except Exception:
                return False, "Photo upload is blocked: invalid approved date format."
        elif hasattr(approved_date_raw, 'year'):
            approved_date = approved_date_raw if isinstance(approved_date_raw, date) else approved_date_raw.date()
        else:
            return False, "Photo upload is blocked: invalid approved date."

        def to_time_obj(val) -> Optional[time]:
            if val is None:
                return None
            if isinstance(val, time):
                return val
            if isinstance(val, timedelta):
                total_sec = int(val.total_seconds())
                h = total_sec // 3600
                m = (total_sec % 3600) // 60
                s = total_sec % 60
                return time(h, m, s)
            if isinstance(val, str):
                parts = val.strip().split(':')
                if len(parts) >= 2:
                    try:
                        h = int(parts[0])
                        m = int(parts[1])
                        s = int(parts[2]) if len(parts) > 2 else 0
                        return time(h, m, s)
                    except ValueError:
                        return None
            return None

        start_time = to_time_obj(start_time_raw)
        end_time = to_time_obj(end_time_raw)

        if start_time is None or end_time is None:
            return False, "Photo upload is blocked: invalid approved start or end time format."

        if start_time >= end_time:
            return False, "Photo upload is blocked: approved start time must precede end time."

        # Date Check
        if approved_date < today_date:
            return False, f"Photo upload is blocked: event concluded on {approved_date.isoformat()}."
        if approved_date > today_date:
            return False, f"Photo upload is blocked: event is scheduled for {approved_date.isoformat()}. Uploads open on the event date."

        # Time Check: start_time <= current_time < end_time
        if current_time < start_time:
            return False, f"Photo upload is blocked: event starts today at {start_time.strftime('%H:%M:%S')}. Uploads open when the event starts."

        if current_time >= end_time:
            return False, f"Photo upload is blocked: event concluded today at {end_time.strftime('%H:%M:%S')}."

        return True, "Event is actively happening live."

    @staticmethod
    def attach_happening_status(event: Dict[str, Any], current_datetime: Optional[Any] = None) -> Dict[str, Any]:
        """Calculates computed_status ('Ongoing', 'Upcoming', 'Completed') and is_happening boolean."""
        if not event:
            return event

        now_dt = current_datetime if current_datetime is not None else EventModel._get_current_time()
        event['server_now'] = now_dt.isoformat()
        event['server_timezone'] = now_dt.tzname() or "UTC"

        is_happening, reason = EventModel.is_event_happening(event, now_dt)
        event['is_happening'] = is_happening
        event['happening_reason'] = reason

        raw_status = (event.get('status') or '').lower()
        if raw_status != 'approved':
            event['computed_status'] = raw_status.capitalize() if raw_status else 'Pending'
            return event

        if is_happening:
            event['computed_status'] = 'Ongoing'
            return event

        approved_date_raw = event.get('approved_date')
        start_time_raw = event.get('approved_start_time')
        end_time_raw = event.get('approved_end_time')

        if approved_date_raw is None or start_time_raw is None or end_time_raw is None:
            event['computed_status'] = 'Upcoming'
            return event

        if isinstance(approved_date_raw, str) and not approved_date_raw.strip():
            event['computed_status'] = 'Upcoming'
            return event
        if isinstance(start_time_raw, str) and not start_time_raw.strip():
            event['computed_status'] = 'Upcoming'
            return event
        if isinstance(end_time_raw, str) and not end_time_raw.strip():
            event['computed_status'] = 'Upcoming'
            return event

        today_date = now_dt.date()
        current_time = now_dt.time()

        try:
            if isinstance(approved_date_raw, str):
                app_date = datetime.strptime(approved_date_raw.split('T')[0], '%Y-%m-%d').date()
            elif hasattr(approved_date_raw, 'year'):
                app_date = approved_date_raw if isinstance(approved_date_raw, date) else approved_date_raw.date()
            else:
                app_date = today_date
        except Exception:
            app_date = today_date

        if app_date < today_date:
            event['computed_status'] = 'Completed'
        elif app_date > today_date:
            event['computed_status'] = 'Upcoming'
        else:
            def parse_time(val):
                if isinstance(val, time):
                    return val
                if isinstance(val, timedelta):
                    sec = int(val.total_seconds())
                    return time(sec // 3600, (sec % 3600) // 60, sec % 60)
                if isinstance(val, str):
                    p = val.strip().split(':')
                    return time(int(p[0]), int(p[1]), int(p[2]) if len(p) > 2 else 0)
                return None

            s_t = parse_time(start_time_raw)
            if s_t and current_time < s_t:
                event['computed_status'] = 'Upcoming'
            else:
                event['computed_status'] = 'Completed'

        return event

    @staticmethod
    def get_by_id(event_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve full event record with organizer, venue, and fest series details."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        e.*,
                        u.name AS organizer_name,
                        u.email AS organizer_email,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity,
                        s.name AS series_name,
                        s.description AS series_description
                    FROM events e
                    JOIN users u ON e.organizer_id = u.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN fest s ON e.series_id = s.id
                    WHERE e.id = %s;
                    """,
                    (event_id,)
                )
                row = cursor.fetchone()
                if row:
                    EventModel.attach_happening_status(row)
                return row
        finally:
            conn.close()

    @staticmethod
    def get_by_organizer(organizer_id: int) -> List[Dict[str, Any]]:
        """Retrieve all events created by a specific organizer with venue and fest details."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        e.*,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        s.name AS series_name,
                        s.description AS series_description
                    FROM events e
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN fest s ON e.series_id = s.id
                    WHERE e.organizer_id = %s
                    ORDER BY e.created_at DESC, e.id DESC;
                    """,
                    (organizer_id,)
                )
                rows = cursor.fetchall()
                for r in rows:
                    EventModel.attach_happening_status(r)
                return rows
        finally:
            conn.close()

    @staticmethod
    def get_all(status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all events for management overview, optionally filtered by status."""
        sql = """
        SELECT 
            e.*,
            u.name AS organizer_name,
            u.email AS organizer_email,
            v.name AS venue_name,
            v.location AS venue_location,
            s.name AS series_name
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        LEFT JOIN venues v ON e.venue_id = v.id
        LEFT JOIN fest s ON e.series_id = s.id
        """
        params = []
        if status:
            sql += " WHERE e.status = %s"
            params.append(status)

        sql += " ORDER BY e.created_at DESC, e.id DESC;"

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_pending_requests() -> List[Dict[str, Any]]:
        """Retrieve pending event requests awaiting management review."""
        return EventModel.get_all(status='pending')

    @staticmethod
    def get_organizer_statistics(organizer_id: int) -> Dict[str, int]:
        """
        Calculates real-time event statistics for a specific organizer.
        Strictly isolated to organizer_id.
        """
        from datetime import date
        today_str = date.today().isoformat()

        sql = """
        SELECT 
            COUNT(*) AS total_events,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_events,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_events,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_events,
            SUM(CASE WHEN status = 'approved' AND approved_date >= %s THEN 1 ELSE 0 END) AS upcoming_events
        FROM events
        WHERE organizer_id = %s;
        """

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (today_str, organizer_id))
                row = cursor.fetchone() or {}
                return {
                    "total_events": int(row.get("total_events") or 0),
                    "pending_events": int(row.get("pending_events") or 0),
                    "approved_events": int(row.get("approved_events") or 0),
                    "rejected_events": int(row.get("rejected_events") or 0),
                    "upcoming_events": int(row.get("upcoming_events") or 0),
                }
        finally:
            conn.close()

    @staticmethod
    def get_administrator_statistics() -> Dict[str, int]:
        """
        Calculates system-wide event statistics across all organizers for administrator.
        """
        from datetime import date
        today_str = date.today().isoformat()

        sql = """
        SELECT 
            COUNT(*) AS total_events,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_events,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_events,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_events,
            SUM(CASE WHEN status = 'approved' AND approved_date >= %s THEN 1 ELSE 0 END) AS upcoming_events
        FROM events;
        """

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (today_str,))
                row = cursor.fetchone() or {}
                return {
                    "total_events": int(row.get("total_events") or 0),
                    "pending_events": int(row.get("pending_events") or 0),
                    "approved_events": int(row.get("approved_events") or 0),
                    "rejected_events": int(row.get("rejected_events") or 0),
                    "upcoming_events": int(row.get("upcoming_events") or 0),
                }
        finally:
            conn.close()

    get_management_statistics = get_administrator_statistics

    @staticmethod
    def get_upcoming_approved_events(limit: int = 10, organizer_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves upcoming approved events (date >= today).
        If organizer_id is provided, strictly filters to that organizer.
        """
        from datetime import date
        today_str = date.today().isoformat()

        sql = """
        SELECT 
            e.id,
            e.event_name,
            e.description,
            e.status,
            e.approved_date,
            e.approved_start_time,
            e.approved_end_time,
            e.created_at,
            u.name AS organizer_name,
            u.email AS organizer_email,
            v.name AS venue_name,
            v.location AS venue_location
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        LEFT JOIN venues v ON e.venue_id = v.id
        WHERE e.status = 'approved' AND e.approved_date >= %s
        """
        params = [today_str]

        if organizer_id is not None:
            sql += " AND e.organizer_id = %s"
            params.append(organizer_id)

        sql += " ORDER BY e.approved_date ASC, e.approved_start_time ASC LIMIT %s;"
        params.append(limit)

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
                for r in rows:
                    EventModel.attach_happening_status(r)
                return rows
        finally:
            conn.close()

    @staticmethod
    def get_approved_events_for_students() -> List[Dict[str, Any]]:
        """
        Retrieve approved/upcoming event details safe for student view.
        Exposes: event_name, description, date, time, venue, status.
        Does not expose internal organizer credentials or pending requests.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        e.id AS event_id,
                        e.event_name,
                        e.description,
                        e.status AS event_status,
                        e.approved_date AS event_date,
                        e.approved_start_time AS start_time,
                        e.approved_end_time AS end_time,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity
                    FROM events e
                    JOIN venues v ON e.venue_id = v.id
                    WHERE e.status = 'approved'
                    ORDER BY e.approved_date ASC, e.approved_start_time ASC;
                    """
                )
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def create_event_request(
        organizer_id: int,
        event_name: str,
        description: str,
        requested_date: str,
        requested_start_time: str,
        requested_end_time: str,
        venue_id: Optional[int] = None,
        category: Optional[str] = 'General',
        series_id: Optional[int] = None
    ) -> int:
        """Create a new event request submitted by an organizer under a fest series."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO events (
                        organizer_id, event_name, description, status,
                        requested_date, requested_start_time, requested_end_time,
                        venue_id, category, series_id
                    ) VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s);
                    """,
                    (organizer_id, event_name.strip(), description.strip(),
                     requested_date, requested_start_time, requested_end_time, venue_id,
                     (category.strip() if category else 'General'), series_id)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def update_status(event_id: int, status: str, rejection_reason: Optional[str] = None) -> bool:
        """Update event status (e.g. approve, reject) and optional rejection reason."""
        if status not in EventModel.STATUSES:
            raise ValueError(f"Invalid status: {status}. Allowed: {EventModel.STATUSES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE events
                    SET status = %s,
                        rejection_reason = %s
                    WHERE id = %s;
                    """,
                    (status, rejection_reason.strip() if rejection_reason else None, event_id)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def allocate_schedule(
        event_id: int,
        venue_id: int,
        approved_date: str,
        approved_start_time: str,
        approved_end_time: str,
        expected_participants: Optional[int] = None
    ) -> bool:
        """
        Management allocation or modification of final venue and schedule.
        Sets status to 'approved' and records final allocation while
        strictly preserving original requested values.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if expected_participants is not None:
                    cursor.execute(
                        """
                        UPDATE events
                        SET status = 'approved',
                            venue_id = %s,
                            approved_date = %s,
                            approved_start_time = %s,
                            approved_end_time = %s,
                            expected_participants = %s,
                            rejection_reason = NULL
                        WHERE id = %s;
                        """,
                        (venue_id, approved_date, approved_start_time, approved_end_time, expected_participants, event_id)
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE events
                        SET status = 'approved',
                            venue_id = %s,
                            approved_date = %s,
                            approved_start_time = %s,
                            approved_end_time = %s,
                            rejection_reason = NULL
                        WHERE id = %s;
                        """,
                        (venue_id, approved_date, approved_start_time, approved_end_time, event_id)
                    )
                return cursor.rowcount > 0
        finally:
            conn.close()

    # Maintain alias for backward compatibility with Stage 2
    approve_event_schedule = allocate_schedule

    @staticmethod
    def get_public_events(
        search: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        series_id: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Public query for student and visitor event discovery.
        Only exposes approved and completed events (hides pending proposals and rejected events).
        Supports search, year, month, category, status, and series filters.
        Includes computed status, festival series name, venue details, and crowd maximum estimates.
        """
        from datetime import date, datetime
        today_date = date.today()
        now_time = datetime.now().time()

        sql = """
        SELECT 
            e.id,
            e.event_name,
            e.description,
            COALESCE(e.category, 'General') AS category,
            e.status AS raw_status,
            COALESCE(e.approved_date, e.requested_date) AS event_date,
            COALESCE(e.approved_date, e.requested_date) AS start_date,
            COALESCE(e.approved_date, e.requested_date) AS end_date,
            COALESCE(e.approved_start_time, e.requested_start_time) AS start_time,
            COALESCE(e.approved_end_time, e.requested_end_time) AS end_time,
            v.id AS venue_id,
            v.name AS venue_name,
            v.location AS venue_location,
            v.capacity AS venue_capacity,
            s.id AS series_id,
            s.name AS series_name,
            crowd_stat.max_crowd,
            crowd_stat.latest_analyzed_at
        FROM events e
        LEFT JOIN venues v ON e.venue_id = v.id
        LEFT JOIN fest s ON e.series_id = s.id
        LEFT JOIN (
            SELECT 
                img.event_id, 
                MAX(ca.predicted_count) AS max_crowd,
                MAX(ca.analysis_timestamp) AS latest_analyzed_at
            FROM images img
            JOIN crowd_analyses ca ON img.id = ca.image_id
            WHERE ca.processing_status = 'completed'
            GROUP BY img.event_id
        ) crowd_stat ON e.id = crowd_stat.event_id
        WHERE e.status IN ('approved', 'completed')
        """
        params: List[Any] = []

        # 1. Search filter
        if search and search.strip():
            query_str = f"%{search.strip()}%"
            sql += " AND (e.event_name LIKE %s OR e.description LIKE %s)"
            params.extend([query_str, query_str])

        # 2. Year filter
        if year:
            sql += " AND YEAR(COALESCE(e.approved_date, e.requested_date)) = %s"
            params.append(int(year))

        # 3. Month filter
        if month:
            sql += " AND MONTH(COALESCE(e.approved_date, e.requested_date)) = %s"
            params.append(int(month))

        # 4. Category filter
        if category and category.strip():
            cat_clean = category.strip()
            if cat_clean.lower() == 'general':
                sql += " AND (e.category = 'General' OR e.category IS NULL OR e.category = '')"
            else:
                sql += " AND LOWER(e.category) = LOWER(%s)"
                params.append(cat_clean)

        # 5. Series filter
        if series_id:
            sql += " AND e.series_id = %s"
            params.append(int(series_id))

        # 6. Status filter
        if status and status.strip():
            st = status.strip().lower()
            if st == 'upcoming':
                sql += """
                AND (
                    e.status = 'approved' AND (
                        COALESCE(e.approved_date, e.requested_date) > CURRENT_DATE() OR
                        (COALESCE(e.approved_date, e.requested_date) = CURRENT_DATE() AND COALESCE(e.approved_start_time, e.requested_start_time) > CURRENT_TIME())
                    )
                )
                """
            elif st == 'ongoing':
                sql += """
                AND (
                    e.status = 'approved' AND 
                    COALESCE(e.approved_date, e.requested_date) = CURRENT_DATE() AND
                    CURRENT_TIME() BETWEEN COALESCE(e.approved_start_time, e.requested_start_time) AND COALESCE(e.approved_end_time, e.requested_end_time)
                )
                """
            elif st == 'completed':
                sql += """
                AND (
                    e.status = 'completed' OR
                    (e.status = 'approved' AND (
                        COALESCE(e.approved_date, e.requested_date) < CURRENT_DATE() OR
                        (COALESCE(e.approved_date, e.requested_date) = CURRENT_DATE() AND COALESCE(e.approved_end_time, e.requested_end_time) < CURRENT_TIME())
                    ))
                )
                """

        # Order logic: completed events show newest first; upcoming/ongoing show earliest first
        if status and status.strip().lower() == 'completed':
            sql += " ORDER BY COALESCE(e.approved_date, e.requested_date) DESC, COALESCE(e.approved_start_time, e.requested_start_time) DESC"
        else:
            sql += " ORDER BY COALESCE(e.approved_date, e.requested_date) ASC, COALESCE(e.approved_start_time, e.requested_start_time) ASC"

        if limit:
            sql += " LIMIT %s"
            params.append(int(limit))

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()

            # Process computed status and crowd status for public presentation
            processed: List[Dict[str, Any]] = []
            for r in rows:
                ev_date = r['event_date']
                s_time = r['start_time']
                e_time = r['end_time']

                # Compute visitor status
                if r['raw_status'] == 'completed':
                    computed_status = 'Completed'
                elif ev_date and ev_date < today_date:
                    computed_status = 'Completed'
                elif ev_date and ev_date == today_date:
                    # Compare time
                    # s_time and e_time can be timedelta or time
                    start_val = (datetime.min + s_time).time() if hasattr(s_time, 'total_seconds') else s_time
                    end_val = (datetime.min + e_time).time() if hasattr(e_time, 'total_seconds') else e_time

                    if end_val and now_time > end_val:
                        computed_status = 'Completed'
                    elif start_val and end_val and start_val <= now_time <= end_val:
                        computed_status = 'Ongoing'
                    else:
                        computed_status = 'Upcoming'
                else:
                    computed_status = 'Upcoming'

                r['computed_status'] = computed_status

                # Compute crowd status
                max_crowd = r['max_crowd']
                cap = r['venue_capacity'] or 0
                if max_crowd is not None:
                    threshold = cap if cap > 0 else 500
                    r['crowd_status'] = 'High Crowd' if max_crowd >= threshold else 'Normal Crowd'
                else:
                    r['crowd_status'] = None

                processed.append(r)

            return processed
        finally:
            conn.close()

    @staticmethod
    def get_public_event_detail(event_id: int) -> Optional[Dict[str, Any]]:
        """
        Public query for a single event detail page.
        Only returns if the event is approved or completed.
        Includes complete venue, series, schedule, and crowd estimation details.
        Does not leak private organizer passwords or internal management alerts.
        """
        from datetime import date, datetime
        today_date = date.today()
        now_time = datetime.now().time()

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        e.id,
                        e.event_name,
                        e.description,
                        COALESCE(e.category, 'General') AS category,
                        e.status AS raw_status,
                        COALESCE(e.approved_date, e.requested_date) AS event_date,
                        COALESCE(e.approved_date, e.requested_date) AS start_date,
                        COALESCE(e.approved_date, e.requested_date) AS end_date,
                        COALESCE(e.approved_start_time, e.requested_start_time) AS start_time,
                        COALESCE(e.approved_end_time, e.requested_end_time) AS end_time,
                        v.id AS venue_id,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity,
                        s.id AS series_id,
                        s.name AS series_name,
                        s.description AS series_description,
                        crowd_stat.max_crowd,
                        crowd_stat.latest_analyzed_at,
                        crowd_stat.total_analyses
                    FROM events e
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN fest s ON e.series_id = s.id
                    LEFT JOIN (
                        SELECT 
                            img.event_id, 
                            MAX(ca.predicted_count) AS max_crowd,
                            MAX(ca.analysis_timestamp) AS latest_analyzed_at,
                            COUNT(ca.id) AS total_analyses
                        FROM images img
                        JOIN crowd_analyses ca ON img.id = ca.image_id
                        WHERE ca.processing_status = 'completed'
                        GROUP BY img.event_id
                    ) crowd_stat ON e.id = crowd_stat.event_id
                    WHERE e.id = %s
                      AND e.status IN ('approved', 'completed');
                """, (event_id,))
                event = cursor.fetchone()
                if not event:
                    return None

                # Compute visitor status
                ev_date = event['event_date']
                s_time = event['start_time']
                e_time = event['end_time']

                if event['raw_status'] == 'completed':
                    computed_status = 'Completed'
                elif ev_date and ev_date < today_date:
                    computed_status = 'Completed'
                elif ev_date and ev_date == today_date:
                    start_val = (datetime.min + s_time).time() if hasattr(s_time, 'total_seconds') else s_time
                    end_val = (datetime.min + e_time).time() if hasattr(e_time, 'total_seconds') else e_time

                    if end_val and now_time > end_val:
                        computed_status = 'Completed'
                    elif start_val and end_val and start_val <= now_time <= end_val:
                        computed_status = 'Ongoing'
                    else:
                        computed_status = 'Upcoming'
                else:
                    computed_status = 'Upcoming'

                event['computed_status'] = computed_status

                # Compute crowd status
                max_crowd = event['max_crowd']
                cap = event['venue_capacity'] or 0
                if max_crowd is not None:
                    threshold = cap if cap > 0 else 500
                    event['crowd_status'] = 'High Crowd' if max_crowd >= threshold else 'Normal Crowd'
                else:
                    event['crowd_status'] = None

                return event
        finally:
            conn.close()

    @staticmethod
    def get_public_categories() -> List[str]:
        """Retrieve distinct event categories present in database."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT COALESCE(category, 'General') AS category
                    FROM events
                    WHERE status IN ('approved', 'completed')
                    ORDER BY category ASC;
                """)
                rows = cursor.fetchall()
                categories = [r['category'] for r in rows if r['category']]
                if 'General' not in categories:
                    categories.append('General')
                return categories
        finally:
            conn.close()

    @staticmethod
    def get_public_years() -> List[int]:
        """Retrieve distinct years for event filtering."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT YEAR(COALESCE(approved_date, requested_date)) AS ev_year
                    FROM events
                    WHERE status IN ('approved', 'completed')
                    ORDER BY ev_year DESC;
                """)
                rows = cursor.fetchall()
                return [r['ev_year'] for r in rows if r['ev_year']]
        finally:
            conn.close()
