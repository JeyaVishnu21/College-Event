
"""
Database Initialization Module
Compatible with local MySQL and managed MySQL services such as Aiven.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Any, Set

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
from config.db import get_db_connection

REQUIRED_TABLES: Set[str] = {
    "users",
    "venues",
    "events",
    "images",
    "crowd_analyses",
    "alerts",
    "fest",
}


def check_database_readiness() -> Dict[str, Any]:
    """Check the configured database without creating or modifying anything."""
    connection = None

    try:
        connection = get_db_connection(include_db=True)

        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            found_tables = {
                list(row.values())[0] for row in cursor.fetchall()
            }

        missing = sorted(REQUIRED_TABLES - found_tables)

        if missing:
            return {
                "ready": False,
                "db_exists": True,
                "missing_tables": missing,
                "message": (
                    f"Database '{settings.DB_NAME}' is reachable, "
                    f"but missing tables: {', '.join(missing)}."
                ),
            }

        return {
            "ready": True,
            "db_exists": True,
            "missing_tables": [],
            "message": (
                f"Database '{settings.DB_NAME}' and all required "
                "tables are ready."
            ),
        }

    except Exception as exc:
        return {
            "ready": False,
            "db_exists": False,
            "missing_tables": sorted(REQUIRED_TABLES),
            "message": (
                f"Unable to check database '{settings.DB_NAME}': "
                f"{type(exc).__name__}: {exc}"
            ),
        }

    finally:
        if connection is not None:
            connection.close()


def initialize_database(verbose: bool = True) -> bool:
    """
    Initialize tables in the already configured database.

    Does not create or switch databases. Existing tables and records
    are preserved by the schema's CREATE TABLE IF NOT EXISTS statements.
    """

    schema_path = BACKEND_DIR / "db" / "schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}"
        )

    with open(schema_path, "r", encoding="utf-8") as file:
        schema_sql = file.read()

    # Remove database creation and database selection statements from
    # the SQL in memory. The original schema.sql remains unchanged.
    schema_sql = re.sub(
        r"(?im)^\s*CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+"
        r"`?crowd_event_db`?\s*"
        r"(?:CHARACTER\s+SET\s+\w+\s*)?"
        r"(?:COLLATE\s+[\w_]+\s*)?;\s*",
        "",
        schema_sql,
    )

    schema_sql = re.sub(
        r"(?im)^\s*USE\s+`?crowd_event_db`?\s*;\s*",
        "",
        schema_sql,
    )

    # Fail safely if an unexpected database-selection statement remains.
    if re.search(
        r"(?im)^\s*(?:CREATE\s+DATABASE|USE\s+`?\w+`?)\b",
        schema_sql,
    ):
        raise RuntimeError(
            "Unexpected database creation or selection statement "
            "in schema.sql. Initialization stopped for safety."
        )

    connection = None

    try:
        if verbose:
            print(f"Initializing tables in '{settings.DB_NAME}'...")

        connection = get_db_connection(
            include_db=True,
            multi_statements=True,
        )

        with connection.cursor() as cursor:
            cursor.execute(schema_sql)

            # Drain any additional result sets from the multi-statement
            # execution before reusing the connection.
            while cursor.nextset():
                pass

        if verbose:
            print("Schema statements executed.")

    except Exception as exc:
        raise RuntimeError(
            f"Failed to initialize '{settings.DB_NAME}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    finally:
        if connection is not None:
            connection.close()

    result = check_database_readiness()

    if not result["ready"]:
        raise RuntimeError(
            f"Database initialization verification failed: "
            f"{result['message']}"
        )

    if verbose:
        print(result["message"])
        print("Database initialization completed.")

    return True
