"""
Database Migration Script (Stage 2)
-----------------------------------
Creates the `crowd_event_db` database if it doesn't exist,
and applies the schema DDL defined in `schema.sql`.
"""

import os
import sys
from pathlib import Path

# Add backend directory to sys.path to allow clean imports
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
from config.init_db import initialize_database


def run_migration():
    """Runs the MySQL schema migration using the unified initialization module."""
    return initialize_database(verbose=True)


if __name__ == '__main__':
    try:
        run_migration()
    except Exception as exc:
        print(f"\n[ERROR] Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
