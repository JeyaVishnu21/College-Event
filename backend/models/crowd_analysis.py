"""
Crowd Analysis Model (Stage 2)
------------------------------
Handles database operations for the `crowd_analyses` table.
Stores numeric crowd estimation results for images.
Provides report aggregation helper to calculate maximum crowd count per event.
"""

from typing import Optional, List, Dict, Any
from config.db import get_db_connection


class CrowdAnalysisModel:
    @staticmethod
    def get_by_id(analysis_id: int) -> Optional[Dict[str, Any]]:
        """Fetch analysis record by ID."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM crowd_analyses WHERE id = %s;",
                    (analysis_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_by_image_id(image_id: int) -> Optional[Dict[str, Any]]:
        """Fetch analysis record associated with a specific image."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM crowd_analyses WHERE image_id = %s;",
                    (image_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_latest_for_event(event_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch the most recent crowd analysis for a specific event.
        Used to determine current crowd level during an active event.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        ca.id AS analysis_id,
                        ca.image_id,
                        ca.predicted_count,
                        ca.analysis_timestamp,
                        img.event_id,
                        img.image_path
                    FROM crowd_analyses ca
                    JOIN images img ON ca.image_id = img.id
                    WHERE img.event_id = %s
                    ORDER BY ca.analysis_timestamp DESC, ca.id DESC
                    LIMIT 1;
                    """,
                    (event_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_event_max_crowd(event_id: int) -> Optional[Dict[str, Any]]:
        """
        Calculates the maximum crowd count among all analyzed images
        belonging to an event for the Stage 2/future crowd report requirement.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        img.event_id,
                        MAX(ca.predicted_count) AS maximum_crowd,
                        MIN(ca.predicted_count) AS minimum_crowd,
                        AVG(ca.predicted_count) AS average_crowd,
                        COUNT(ca.id) AS total_analyses
                    FROM crowd_analyses ca
                    JOIN images img ON ca.image_id = img.id
                    WHERE img.event_id = %s
                    GROUP BY img.event_id;
                    """,
                    (event_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def create_analysis(
        image_id: int,
        predicted_count: int,
        processing_status: str = 'completed',
        model_name: str = 'CSRNet'
    ) -> int:
        """Insert a new crowd analysis record for an image."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO crowd_analyses (
                        image_id, predicted_count, processing_status, model_name
                    ) VALUES (%s, %s, %s, %s);
                    """,
                    (image_id, predicted_count, processing_status, model_name)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def upsert_analysis(
        image_id: int,
        predicted_count: int,
        processing_status: str = 'completed',
        model_name: str = 'CSRNet'
    ) -> int:
        """
        Safely inserts or updates a crowd analysis record for an image.
        Respects the UNIQUE(image_id) constraint across repeated requests.
        """
        existing = CrowdAnalysisModel.get_by_image_id(image_id)
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if existing:
                    cursor.execute(
                        """
                        UPDATE crowd_analyses
                        SET predicted_count = %s,
                            processing_status = %s,
                            model_name = %s,
                            analysis_timestamp = CURRENT_TIMESTAMP
                        WHERE image_id = %s;
                        """,
                        (predicted_count, processing_status, model_name, image_id)
                    )
                    return existing['id']
                else:
                    cursor.execute(
                        """
                        INSERT INTO crowd_analyses (
                            image_id, predicted_count, processing_status, model_name
                        ) VALUES (%s, %s, %s, %s);
                        """,
                        (image_id, predicted_count, processing_status, model_name)
                    )
                    return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def update_status(image_id: int, processing_status: str) -> bool:
        """Update the processing status of an analysis record."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE crowd_analyses SET processing_status = %s WHERE image_id = %s;",
                    (processing_status, image_id)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

