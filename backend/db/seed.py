"""
Database Seed Script (Stage 2)
------------------------------
Populates the `crowd_event_db` database with sample data
defined in `seed.sql` and validates the resulting records.
"""

import sys
from pathlib import Path

# Add backend directory to sys.path to allow clean imports
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
from config.db import get_db_connection


def run_seed():
    """Seeds the MySQL database with initial test records."""
    seed_path = BACKEND_DIR / 'db' / 'seed.sql'
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found at: {seed_path}")

    with open(seed_path, 'r', encoding='utf-8') as f:
        seed_sql = f.read()

    print("==================================================")
    print(" Crowd Event Management System — Stage 2 Seeding  ")
    print(f" Target Database: {settings.DB_NAME}")
    print("==================================================")

    # Execute seed script with multi-statement support
    conn = get_db_connection(include_db=True, multi_statements=True)
    with conn.cursor() as cursor:
        cursor.execute(seed_sql)
    conn.close()

    # Verify seeded counts
    conn = get_db_connection(include_db=True)
    with conn.cursor() as cursor:
        cursor.execute("SELECT role, COUNT(*) AS count FROM users GROUP BY role;")
        user_counts = {row['role']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) AS count FROM venues;")
        venue_count = cursor.fetchone()['count']

        cursor.execute("SELECT status, COUNT(*) AS count FROM events GROUP BY status;")
        event_counts = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT processing_status, COUNT(*) AS count FROM images GROUP BY processing_status;")
        image_counts = {row['processing_status']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) AS count FROM crowd_analyses;")
        analyses_count = cursor.fetchone()['count']

        cursor.execute("SELECT MAX(predicted_count) AS max_crowd FROM crowd_analyses ca JOIN images img ON ca.image_id = img.id WHERE img.event_id = 1;")
        max_crowd = cursor.fetchone()['max_crowd']

        cursor.execute("SELECT COUNT(*) AS count FROM alerts;")
        alert_count = cursor.fetchone()['count']
    conn.close()

    print("Seeded Records Summary:")
    admin_count = user_counts.get('administrator', 0) or user_counts.get('management', 0)
    print(f"   [OK] Users:        Administrator: {admin_count}, Organizers: {user_counts.get('organizer', 0)}")
    print(f"   [OK] Venues:       {venue_count} venues")
    print(f"   [OK] Events:       Approved: {event_counts.get('approved', 0)}, Pending: {event_counts.get('pending', 0)}")
    print(f"   [OK] Images:       Completed: {image_counts.get('completed', 0)}, Pending: {image_counts.get('pending', 0)}")
    print(f"   [OK] Analyses:     {analyses_count} crowd analyses (Max count: {max_crowd})")
    print(f"   [OK] Alerts:       {alert_count} safety alerts")

    print("==================================================")
    print(" Stage 2 Seed Data Applied Successfully!          ")
    print("==================================================")


if __name__ == '__main__':
    try:
        run_seed()
    except Exception as exc:
        print(f"\n[ERROR] Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)
