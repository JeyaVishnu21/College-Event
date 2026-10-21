"""
Image Model (Stage 2)
---------------------
Handles database operations for the `images` table.
An event has many images uploaded periodically during an event.
An image has zero or one crowd analysis record.
"""

from typing import Optional, List, Dict, Any
from config.db import get_db_connection


class ImageModel:
    STATUSES = ['pending', 'processing', 'completed', 'failed']

    @staticmethod
    def get_by_id(image_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific image record by ID."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, event_id, image_path, uploaded_at, processing_status, created_at FROM images WHERE id = %s;",
                    (image_id,)
                )
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_images_by_event(event_id: int) -> List[Dict[str, Any]]:
        """Retrieve all images associated with a specific event."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        img.id AS image_id,
                        img.event_id,
                        img.image_path,
                        img.uploaded_at,
                        img.processing_status,
                        ca.id AS analysis_id,
                        ca.predicted_count,
                        ca.analysis_timestamp
                    FROM images img
                    LEFT JOIN crowd_analyses ca ON img.id = ca.image_id
                    WHERE img.event_id = %s
                    ORDER BY img.uploaded_at DESC, img.id DESC;
                    """,
                    (event_id,)
                )
                return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def create_image(event_id: int, image_path: str, processing_status: str = 'pending') -> int:
        """Record a new uploaded image for an event."""
        if processing_status not in ImageModel.STATUSES:
            raise ValueError(f"Invalid status: {processing_status}. Allowed: {ImageModel.STATUSES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO images (event_id, image_path, processing_status)
                    VALUES (%s, %s, %s);
                    """,
                    (event_id, image_path.strip(), processing_status)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def update_processing_status(image_id: int, status: str) -> bool:
        """Update processing status of an image (e.g. pending -> processing -> completed)."""
        if status not in ImageModel.STATUSES:
            raise ValueError(f"Invalid status: {status}. Allowed: {ImageModel.STATUSES}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE images SET processing_status = %s WHERE id = %s;",
                    (status, image_id)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def delete_image(image_id: int) -> bool:
        """Delete an image record from database (e.g. rollback/cleanup)."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM images WHERE id = %s;", (image_id,))
                return cursor.rowcount > 0
        finally:
            conn.close()
