"""
Database Initialization Module (Stage 2)
----------------------------------------
Provides dedicated, idempotent, and non-destructive initialization for the
Crowd Event Management System database (`crowd_event_db`).

Features:
1. Connects to MySQL Server without specifying a database to ensure `crowd_event_db` exists.
2. Re-uses the project's canonical `backend/db/schema.sql` (which uses CREATE TABLE IF NOT EXISTS).
3. Preserves all existing tables and data (does NOT drop or overwrite records).
4. Verifies the existence of all 6 required Stage 2 tables:
   - users, venues, events, images, crowd_analyses, alerts.
5. Provides both full initialization (`initialize_database`) and lightweight
   readiness checking (`check_database_readiness`) for application startup.
6. Does NOT expose MySQL passwords in logs or terminal outputs.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Set

# Ensure backend directory is in sys.path for clean imports
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
from config.db import get_db_connection

REQUIRED_TABLES: Set[str] = {
    'users',
    'venues',
    'events',
    'images',
    'crowd_analyses',
    'alerts',
    'fest'
}


def check_database_readiness() -> Dict[str, Any]:
    """
    Lightweight check to determine if the target MySQL database and tables exist.
    Does NOT execute schema.sql. Suitable for application boot checks.
    """
    try:
        # First check if database exists
        server_conn = get_db_connection(include_db=False)
        with server_conn.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s;",
                (settings.DB_NAME,)
            )
            db_exists = cursor.fetchone() is not None
        server_conn.close()

        if not db_exists:
            return {
                "ready": False,
                "db_exists": False,
                "missing_tables": list(REQUIRED_TABLES),
                "message": f"Database '{settings.DB_NAME}' does not exist on {settings.DB_HOST}:{settings.DB_PORT}."
            }

        # Check existing tables in target database
        db_conn = get_db_connection(include_db=True)
        with db_conn.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            found_tables = {list(row.values())[0] for row in cursor.fetchall()}
        db_conn.close()

        missing = REQUIRED_TABLES - found_tables
        if missing:
            return {
                "ready": False,
                "db_exists": True,
                "missing_tables": sorted(list(missing)),
                "message": f"Database exists but missing {len(missing)} required table(s): {', '.join(sorted(missing))}."
            }

        return {
            "ready": True,
            "db_exists": True,
            "missing_tables": [],
            "message": f"Database '{settings.DB_NAME}' and all required tables are ready on {settings.DB_HOST}:{settings.DB_PORT}."
        }

    except Exception as exc:
        return {
            "ready": False,
            "db_exists": False,
            "missing_tables": list(REQUIRED_TABLES),
            "message": f"MySQL server check error on {settings.DB_HOST}:{settings.DB_PORT}: {str(exc)}"
        }


def initialize_database(verbose: bool = True) -> bool:
    """
    Idempotent database setup:
    1. Connects to MySQL server without selecting a database.
    2. Executes CREATE DATABASE IF NOT EXISTS `crowd_event_db`.
    3. Reconnects to `crowd_event_db` with multi_statements=True.
    4. Executes the canonical `backend/db/schema.sql`.
    5. Verifies all required tables exist.
    
    Safe to execute multiple times. Does NOT drop or truncate tables.
    """
    schema_path = BACKEND_DIR / 'db' / 'schema.sql'
    if not schema_path.exists():
        raise FileNotFoundError(f"Canonical schema file not found at: {schema_path}")

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    if verbose:
        print("==================================================")
        print(" Crowd Event Management System — Database Setup   ")
        print(f" Target Host:     {settings.DB_HOST}:{settings.DB_PORT}")
        print(f" Target User:     {settings.DB_USER}")
        print(f" Target Database: {settings.DB_NAME}")
        print("==================================================")

    # Step 1: Connect to server without database to create DB if missing
    if verbose:
        print("1. Ensuring database exists...")
    try:
        server_conn = get_db_connection(include_db=False)
        with server_conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        server_conn.close()
        if verbose:
            print(f"   [OK] Database `{settings.DB_NAME}` is ready.")
    except Exception as exc:
        err_msg = f"Failed to connect to MySQL server at {settings.DB_HOST}:{settings.DB_PORT}: {str(exc)}"
        if verbose:
            print(f"   [ERROR] {err_msg}", file=sys.stderr)
        raise RuntimeError(err_msg) from exc

    # Step 2: Apply schema using canonical schema.sql
    if verbose:
        print("2. Applying Stage 2 schema tables, foreign keys, and indexes...")
    try:
        db_conn = get_db_connection(include_db=True, multi_statements=True)
        with db_conn.cursor() as cursor:
            cursor.execute(schema_sql)
        db_conn.close()
        if verbose:
            print("   [OK] Schema definition executed successfully.")
    except Exception as exc:
        err_msg = f"Failed to execute schema.sql in `{settings.DB_NAME}`: {str(exc)}"
        if verbose:
            print(f"   [ERROR] {err_msg}", file=sys.stderr)
        raise RuntimeError(err_msg) from exc

    # Step 3: Verify all required tables exist
    if verbose:
        print("3. Verifying required tables...")
    db_conn = get_db_connection(include_db=True)
    with db_conn.cursor() as cursor:
        cursor.execute("SHOW TABLES;")
        existing_tables = {list(row.values())[0] for row in cursor.fetchall()}
    db_conn.close()

    missing = REQUIRED_TABLES - existing_tables
    if missing:
        err_msg = f"Database initialization incomplete. Missing tables: {missing}"
        if verbose:
            print(f"   [ERROR] {err_msg}", file=sys.stderr)
        raise RuntimeError(err_msg)

    if verbose:
        print(f"   [OK] Verified {len(existing_tables)} tables in `{settings.DB_NAME}`:")
        for t in sorted(existing_tables):
            marker = "[REQUIRED]" if t in REQUIRED_TABLES else "[EXTRA]"
            print(f"        - {t} {marker}")
        print("==================================================")
        print(" Database Initialization Completed Successfully!  ")
        print("==================================================")

    return True


if __name__ == '__main__':
    try:
        success = initialize_database(verbose=True)
        sys.exit(0 if success else 1)
    except Exception as err:
        print(f"\n[FATAL] Database initialization failed: {err}", file=sys.stderr)
        sys.exit(1)
