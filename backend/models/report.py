"""
Report Model (Stage 8)
----------------------
Handles database aggregations and queries for event crowd analytics and audit reports.
Computes real-time peak density, capacity utilization, chronological analysis history,
and threshold alerts directly from MySQL database records.
"""

from typing import Optional, List, Dict, Any
from config.db import get_db_connection


def compute_crowd_level(count: Optional[int], capacity: Optional[int]) -> str:
    """Classifies crowd density level based on venue capacity utilization."""
    if count is None:
        return "No Data"
    if capacity and capacity > 0:
        util = (count / capacity) * 100
        if util <= 50:
            return "Safe (Low)"
        elif util <= 85:
            return "Moderate"
        elif util <= 100:
            return "High (Near Capacity)"
        else:
            return "Critical (Overcapacity)"
    else:
        if count < 50:
            return "Low"
        elif count < 200:
            return "Moderate"
        elif count < 500:
            return "High"
        else:
            return "Critical / Dense"


class ReportModel:
    @staticmethod
    def get_accessible_events(user_id: Optional[int], role: str) -> List[Dict[str, Any]]:
        """
        Retrieves list of events accessible to the user with summary indicators.
        Organizers only see their own events; administrators see all events.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                is_admin = role in ('administrator', 'management')
                if is_admin:
                    query = """
                    SELECT 
                        e.id,
                        e.event_name,
                        e.organizer_id,
                        u.name AS organizer_name,
                        u.email AS organizer_email,
                        e.status,
                        e.venue_id,
                        v.name AS venue_name,
                        v.capacity AS venue_capacity,
                        e.requested_date,
                        e.approved_date,
                        e.approved_start_time,
                        e.approved_end_time,
                        COUNT(DISTINCT img.id) AS total_images,
                        COUNT(DISTINCT CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.id 
                        END) AS analyzed_images,
                        MAX(CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.predicted_count 
                        END) AS max_crowd,
                        COUNT(DISTINCT a.id) AS alerts_count
                    FROM events e
                    JOIN users u ON e.organizer_id = u.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN images img ON e.id = img.event_id
                    LEFT JOIN crowd_analyses ca ON img.id = ca.image_id
                    LEFT JOIN alerts a ON e.id = a.event_id
                    GROUP BY e.id, u.name, u.email, v.name, v.capacity
                    ORDER BY (analyzed_images > 0) DESC, COALESCE(e.approved_date, e.requested_date) DESC, e.id DESC;
                    """
                    cursor.execute(query)
                else:
                    query = """
                    SELECT 
                        e.id,
                        e.event_name,
                        e.organizer_id,
                        u.name AS organizer_name,
                        u.email AS organizer_email,
                        e.status,
                        e.venue_id,
                        v.name AS venue_name,
                        v.capacity AS venue_capacity,
                        e.requested_date,
                        e.approved_date,
                        e.approved_start_time,
                        e.approved_end_time,
                        COUNT(DISTINCT img.id) AS total_images,
                        COUNT(DISTINCT CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.id 
                        END) AS analyzed_images,
                        MAX(CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.predicted_count 
                        END) AS max_crowd,
                        COUNT(DISTINCT a.id) AS alerts_count
                    FROM events e
                    JOIN users u ON e.organizer_id = u.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN images img ON e.id = img.event_id
                    LEFT JOIN crowd_analyses ca ON img.id = ca.image_id
                    LEFT JOIN alerts a ON e.id = a.event_id
                    WHERE e.organizer_id = %s
                    GROUP BY e.id, u.name, u.email, v.name, v.capacity
                    ORDER BY (analyzed_images > 0) DESC, COALESCE(e.approved_date, e.requested_date) DESC, e.id DESC;
                    """
                    cursor.execute(query, (user_id,))
                
                rows = cursor.fetchall()
                for r in rows:
                    cap = r.get('venue_capacity')
                    mx = r.get('max_crowd')
                    if cap and cap > 0 and mx is not None:
                        r['peak_utilization_percent'] = round((mx / cap) * 100, 1)
                    else:
                        r['peak_utilization_percent'] = None
                return rows
        finally:
            conn.close()

    @staticmethod
    def get_event_report(event_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves the complete report bundle for a specific event:
        metadata, summary statistics, chronological history, and alerts.
        Returns None if event does not exist.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 1. Fetch Event, Venue, Organizer & Fest details
                cursor.execute(
                    """
                    SELECT 
                        e.id,
                        e.event_name,
                        e.description,
                        e.status,
                        e.category,
                        e.organizer_id,
                        u.name AS organizer_name,
                        u.email AS organizer_email,
                        e.venue_id,
                        v.name AS venue_name,
                        v.location AS venue_location,
                        v.capacity AS venue_capacity,
                        e.requested_date,
                        e.requested_start_time,
                        e.requested_end_time,
                        e.approved_date,
                        e.approved_start_time,
                        e.approved_end_time,
                        e.series_id,
                        f.name AS series_name,
                        e.created_at,
                        e.updated_at
                    FROM events e
                    JOIN users u ON e.organizer_id = u.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    LEFT JOIN fest f ON e.series_id = f.id
                    WHERE e.id = %s;
                    """,
                    (event_id,)
                )
                event = cursor.fetchone()
                if not event:
                    return None

                # 2. Fetch Crowd Analysis Summary Statistics
                cursor.execute(
                    """
                    SELECT 
                        COUNT(img.id) AS total_images,
                        COUNT(CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN 1 
                        END) AS analyzed_images,
                        COUNT(CASE 
                            WHEN img.processing_status IN ('pending', 'processing') OR ca.processing_status = 'pending' 
                            THEN 1 
                        END) AS pending_images,
                        COUNT(CASE 
                            WHEN img.processing_status = 'failed' OR ca.processing_status = 'failed' 
                            THEN 1 
                        END) AS failed_images,
                        MAX(CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.predicted_count 
                        END) AS max_crowd,
                        MIN(CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.predicted_count 
                        END) AS min_crowd,
                        ROUND(AVG(CASE 
                            WHEN ca.processing_status = 'completed' AND img.processing_status = 'completed' 
                            THEN ca.predicted_count 
                        END), 1) AS avg_crowd
                    FROM images img
                    LEFT JOIN crowd_analyses ca ON img.id = ca.image_id
                    WHERE img.event_id = %s;
                    """,
                    (event_id,)
                )
                stats = cursor.fetchone() or {
                    "total_images": 0,
                    "analyzed_images": 0,
                    "pending_images": 0,
                    "failed_images": 0,
                    "max_crowd": None,
                    "min_crowd": None,
                    "avg_crowd": None
                }

                # 3. Fetch Chronological Analysis History
                cursor.execute(
                    """
                    SELECT 
                        ca.id AS analysis_id,
                        ca.image_id,
                        ca.predicted_count,
                        ca.analysis_timestamp,
                        ca.processing_status,
                        ca.model_name,
                        img.image_path,
                        img.uploaded_at
                    FROM crowd_analyses ca
                    JOIN images img ON ca.image_id = img.id
                    WHERE img.event_id = %s 
                      AND ca.processing_status = 'completed' 
                      AND img.processing_status = 'completed'
                    ORDER BY ca.analysis_timestamp ASC, ca.id ASC;
                    """,
                    (event_id,)
                )
                history = list(cursor.fetchall())

                # 4. Fetch Actual Crowd Alerts
                cursor.execute(
                    """
                    SELECT 
                        a.id,
                        a.detected_count,
                        a.threshold,
                        a.message,
                        a.status,
                        a.created_at,
                        u.name AS recipient_name,
                        u.role AS recipient_role
                    FROM alerts a
                    JOIN users u ON a.user_id = u.id
                    WHERE a.event_id = %s
                    ORDER BY a.created_at ASC, a.id ASC;
                    """,
                    (event_id,)
                )
                alerts = list(cursor.fetchall())

                # 5. Compute Key Metrics
                capacity = event.get('venue_capacity')
                max_crowd = stats.get('max_crowd')
                analyzed_count = stats.get('analyzed_images', 0)
                has_data = analyzed_count > 0 and max_crowd is not None

                if capacity and capacity > 0 and max_crowd is not None:
                    peak_utilization = round((max_crowd / capacity) * 100, 1)
                else:
                    peak_utilization = None

                highest_crowd_level = compute_crowd_level(max_crowd, capacity) if has_data else "No Data"

                # Enrich history records with individual utilization and level
                for h in history:
                    cnt = h.get('predicted_count', 0)
                    if capacity and capacity > 0:
                        h['utilization_percent'] = round((cnt / capacity) * 100, 1)
                    else:
                        h['utilization_percent'] = None
                    h['crowd_level'] = compute_crowd_level(cnt, capacity)

                avg_crowd = float(stats['avg_crowd']) if stats.get('avg_crowd') is not None else None

                summary = {
                    "total_images": stats.get('total_images', 0),
                    "analyzed_images": analyzed_count,
                    "pending_images": stats.get('pending_images', 0),
                    "failed_images": stats.get('failed_images', 0),
                    "max_crowd": max_crowd,
                    "min_crowd": stats.get('min_crowd'),
                    "avg_crowd": avg_crowd,
                    "venue_capacity": capacity,
                    "peak_utilization_percent": peak_utilization,
                    "highest_crowd_level": highest_crowd_level,
                    "alerts_count": len(alerts),
                    "has_data": has_data
                }

                return {
                    "event": event,
                    "summary": summary,
                    "history": history,
                    "alerts": alerts
                }
        finally:
            conn.close()
