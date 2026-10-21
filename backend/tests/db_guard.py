"""
Test Database Isolation and Safety Guard Infrastructure
-------------------------------------------------------
Provides:
1. Strict Safety Guard: Prevents ANY automated test from executing modifying
   or destructive SQL statements (DELETE, TRUNCATE, DROP, UPDATE, INSERT, ALTER)
   against the real development database (`crowd_event_db`).
2. Isolated Test Database: Provides high-fidelity, in-memory SQLite database
   mimicking MySQL PyMySQL connection and DictCursor, ensuring complete isolation.
3. Transparent monkeypatching helper for tests.
"""

import re
import sys
import sqlite3
from datetime import date, datetime, time, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
import config.db
from middleware.auth import hash_password

PROTECTED_DATABASES = {
    'crowd_event_db',
    str(settings.DB_NAME).lower(),
}

DESTRUCTIVE_PATTERN = re.compile(
    r'^\s*(DELETE\s+FROM|TRUNCATE(\s+TABLE)?|DROP\s+(DATABASE|TABLE|VIEW)|INSERT\s+INTO|UPDATE\s+\w+\s+SET|ALTER\s+TABLE|REPLACE\s+INTO)',
    re.IGNORECASE
)


class DatabaseSafetyGuardError(RuntimeError):
    """Raised when an automated test attempts a modifying operation against a protected database."""
    pass


class ProtectedPyMySQLCursorWrapper:
    """
    Wraps a real PyMySQL cursor to intercept and block any destructive or modifying SQL
    if the connection targets the protected development database (`crowd_event_db`).
    """
    def __init__(self, real_cursor, db_name: str):
        self._cursor = real_cursor
        self._db_name = str(db_name or '').lower()

    def execute(self, query, params=None):
        clean_q = query.strip() if isinstance(query, str) else str(query).strip()
        if self._db_name in PROTECTED_DATABASES and DESTRUCTIVE_PATTERN.match(clean_q):
            raise DatabaseSafetyGuardError(
                f"\n{'='*80}\n"
                f"[CRITICAL SAFETY GUARD VIOLATION]\n"
                f"Automated test attempted to execute a modifying query against protected database '{self._db_name}':\n"
                f"SQL: {clean_q[:120]}...\n"
                f"Tests are strictly forbidden from modifying or deleting '{self._db_name}'.\n"
                f"Tests must use IsolatedTestDatabase instead.\n"
                f"{'='*80}"
            )
        if params is not None:
            return self._cursor.execute(query, params)
        return self._cursor.execute(query)

    def executemany(self, query, seq_of_params):
        clean_q = query.strip() if isinstance(query, str) else str(query).strip()
        if self._db_name in PROTECTED_DATABASES and DESTRUCTIVE_PATTERN.match(clean_q):
            raise DatabaseSafetyGuardError(
                f"\n{'='*80}\n"
                f"[CRITICAL SAFETY GUARD VIOLATION]\n"
                f"Automated test attempted to execute a modifying query against protected database '{self._db_name}':\n"
                f"SQL: {clean_q[:120]}...\n"
                f"Tests are strictly forbidden from modifying or deleting '{self._db_name}'.\n"
                f"Tests must use IsolatedTestDatabase instead.\n"
                f"{'='*80}"
            )
        return self._cursor.executemany(query, seq_of_params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self._cursor, '__exit__'):
            return self._cursor.__exit__(exc_type, exc_val, exc_tb)
        return False


class ProtectedPyMySQLConnectionWrapper:
    """Wraps a PyMySQL connection object to return ProtectedPyMySQLCursorWrapper."""
    def __init__(self, real_conn, db_name: str):
        self._conn = real_conn
        self._db_name = db_name

    def cursor(self, *args, **kwargs):
        real_cur = self._conn.cursor(*args, **kwargs)
        return ProtectedPyMySQLCursorWrapper(real_cur, self._db_name)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self._conn, '__exit__'):
            return self._conn.__exit__(exc_type, exc_val, exc_tb)
        return False


# Track whether the safety guard has been installed globally
_GUARD_INSTALLED = False
_ORIGINAL_GET_DB_CONN = config.db.get_db_connection


def install_global_safety_guard():
    """Installs the safety guard on config.db.get_db_connection and pymysql.connect."""
    global _GUARD_INSTALLED, _ORIGINAL_GET_DB_CONN
    if _GUARD_INSTALLED:
        return

    _ORIGINAL_GET_DB_CONN = config.db.get_db_connection

    def guarded_get_db_connection(include_db: bool = True, multi_statements: bool = False):
        conn = _ORIGINAL_GET_DB_CONN(include_db=include_db, multi_statements=multi_statements)
        db_name = settings.DB_NAME if include_db else ""
        return ProtectedPyMySQLConnectionWrapper(conn, db_name)

    config.db.get_db_connection = guarded_get_db_connection
    _GUARD_INSTALLED = True


class SQLitePyMySQLCursorAdapter:
    """Adapts an in-memory SQLite cursor to mimic PyMySQL DictCursor with %s and MySQL syntax support."""
    def __init__(self, sqlite_conn):
        self._conn = sqlite_conn
        self._cur = sqlite_conn.cursor()

    def execute(self, query, params=None):
        q = str(query).strip()
        # 1. Translate ON DUPLICATE KEY UPDATE to INSERT OR REPLACE INTO for SQLite
        if 'ON DUPLICATE KEY UPDATE' in q.upper():
            q = re.sub(r'ON\s+DUPLICATE\s+KEY\s+UPDATE.*$', '', q, flags=re.IGNORECASE | re.DOTALL)
            q = re.sub(r'^\s*INSERT\s+INTO', 'INSERT OR REPLACE INTO', q, flags=re.IGNORECASE)

        # 2. Translate MySQL datetime keywords with () to SQLite compatible functions
        q = re.sub(r'\bCURRENT_DATE\(\)', "date('now')", q, flags=re.IGNORECASE)
        q = re.sub(r'\bCURRENT_TIME\(\)', "time('now')", q, flags=re.IGNORECASE)
        q = re.sub(r'\bNOW\(\)', "datetime('now')", q, flags=re.IGNORECASE)

        # 3. Translate %s placeholder to ?
        sqlite_query = q.replace('%s', '?')

        if params is not None:
            # Flatten or format params if necessary
            if isinstance(params, (list, tuple)):
                clean_params = []
                for p in params:
                    if isinstance(p, (date, datetime, time)):
                        clean_params.append(p.isoformat())
                    else:
                        clean_params.append(p)
                res = self._cur.execute(sqlite_query, tuple(clean_params))
            else:
                res = self._cur.execute(sqlite_query, params)
        else:
            res = self._cur.execute(sqlite_query)

        self._conn.commit()
        return res

    def executemany(self, query, seq_of_params):
        for params in seq_of_params:
            self.execute(query, params)
        return self

    @staticmethod
    def _convert_value(val):
        if isinstance(val, str):
            if re.match(r'^\d{4}-\d{2}-\d{2}$', val):
                try:
                    return datetime.strptime(val, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif re.match(r'^\d{2}:\d{2}:\d{2}$', val):
                try:
                    parts = [int(p) for p in val.split(':')]
                    return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
                except (ValueError, IndexError):
                    pass
            elif re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', val):
                try:
                    return datetime.strptime(val[:19], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
        return val

    @classmethod
    def _convert_row(cls, row):
        if row is None:
            return None
        d = dict(row)
        for k, v in d.items():
            d[k] = cls._convert_value(v)
        return d

    def fetchone(self):
        row = self._cur.fetchone()
        return self._convert_row(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [self._convert_row(r) for r in rows]

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SQLitePyMySQLConnectionAdapter:
    """Adapts an in-memory SQLite connection to mimic PyMySQL Connection."""
    def __init__(self, sqlite_conn):
        self._conn = sqlite_conn

    def cursor(self, *args, **kwargs):
        return SQLitePyMySQLCursorAdapter(self._conn)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # In-memory DB persists for the test class session; do not close prematurely
        pass


class IsolatedTestDatabase:
    """
    Manages an isolated in-memory SQLite test database.
    Provides complete schema setup, seed population, and model patching.
    """
    def __init__(self):
        self.sqlite_conn = None
        self._original_conns = {}

    def init_database(self) -> sqlite3.Connection:
        self.sqlite_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.sqlite_conn.row_factory = sqlite3.Row

        # Register MySQL compatibility functions
        self.sqlite_conn.create_function("YEAR", 1, lambda d: int(str(d).split('-')[0]) if d else None)
        self.sqlite_conn.create_function("MONTH", 1, lambda d: int(str(d).split('-')[1]) if d else None)

        cur = self.sqlite_conn.cursor()
        cur.executescript("""
            PRAGMA foreign_keys = OFF;

            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT CHECK(role IN ('administrator', 'management', 'organizer')) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                capacity INTEGER NOT NULL DEFAULT 0,
                status TEXT CHECK(status IN ('available', 'unavailable')) DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE fest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                start_date DATE,
                end_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIEW event_series AS SELECT * FROM fest;

            CREATE TRIGGER event_series_insert INSTEAD OF INSERT ON event_series
            BEGIN
                INSERT INTO fest (id, name, description, start_date, end_date, created_at, updated_at)
                VALUES (new.id, new.name, new.description, new.start_date, new.end_date, coalesce(new.created_at, datetime('now')), coalesce(new.updated_at, datetime('now')));
            END;

            CREATE TRIGGER event_series_delete INSTEAD OF DELETE ON event_series
            BEGIN
                DELETE FROM fest WHERE (old.id IS NOT NULL AND id = old.id) OR (old.id IS NULL);
            END;

            CREATE TRIGGER event_series_update INSTEAD OF UPDATE ON event_series
            BEGIN
                UPDATE fest SET name = new.name, description = new.description, start_date = new.start_date, end_date = new.end_date, updated_at = coalesce(new.updated_at, datetime('now'))
                WHERE id = old.id;
            END;

            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER,
                organizer_id INTEGER NOT NULL,
                venue_id INTEGER,
                event_name TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending', 'approved', 'rejected', 'completed', 'cancelled')) DEFAULT 'pending',
                rejection_reason TEXT,
                requested_date DATE NOT NULL,
                requested_start_time TIME NOT NULL,
                requested_end_time TIME NOT NULL,
                approved_date DATE,
                approved_start_time TIME,
                approved_end_time TIME,
                expected_participants INTEGER,
                category TEXT DEFAULT 'General',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (series_id) REFERENCES fest(id),
                FOREIGN KEY (organizer_id) REFERENCES users(id),
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );

            CREATE TABLE images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_status TEXT CHECK(processing_status IN ('pending', 'processing', 'completed', 'failed')) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id)
            );

            CREATE TABLE crowd_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                predicted_count INTEGER NOT NULL,
                analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_status TEXT DEFAULT 'completed',
                model_name TEXT DEFAULT 'CSRNet',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id)
            );

            CREATE TABLE alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                crowd_analysis_id INTEGER,
                detected_count INTEGER NOT NULL,
                threshold INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT CHECK(status IN ('unread', 'read')) DEFAULT 'unread',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (crowd_analysis_id) REFERENCES crowd_analyses(id)
            );
        """)
        self.sqlite_conn.commit()
        return self.sqlite_conn

    def seed_baseline(self):
        """Seeds standard baseline users and venues into the isolated test database."""
        if not self.sqlite_conn:
            self.init_database()

        cur = self.sqlite_conn.cursor()
        admin_hash = hash_password("Admin@123")
        org_hash = hash_password("Organizer@123")
        org2_hash = hash_password("Organizer2@123")
        stu_hash = hash_password("Student@123")

        # 1. Base Users
        cur.executemany("""
            INSERT OR REPLACE INTO users (id, name, email, password_hash, role)
            VALUES (?, ?, ?, ?, ?);
        """, [
            (1, "Admin Management", "admin@college.edu", admin_hash, "management"),
            (2, "John Organizer", "john.organizer@college.edu", org_hash, "organizer"),
            (3, "Sarah Organizer", "sarah.organizer@college.edu", org2_hash, "organizer")
        ])

        # 2. Base Venues
        cur.executemany("""
            INSERT OR REPLACE INTO venues (id, name, location, capacity, status)
            VALUES (?, ?, ?, ?, ?);
        """, [
            (1, "Main Auditorium", "Block A, 1st Floor", 1000, "available"),
            (2, "Seminar Hall", "Block B, 2nd Floor", 250, "available"),
            (3, "Open Ground", "Campus Central Grounds", 3000, "available")
        ])

        # 3. Base Fests
        cur.executemany("""
            INSERT OR REPLACE INTO fest (id, name, description, start_date, end_date)
            VALUES (?, ?, ?, ?, ?);
        """, [
            (1, "TechFest 2026", "Annual Technology Festival", "2026-10-01", "2026-10-31"),
            (2, "CulturalFest 2026", "Annual Cultural Festival", "2026-11-01", "2026-11-30")
        ])

        self.sqlite_conn.commit()

    def patch_models(self):
        """Monkeypatches config.db and all modules/models to direct traffic to this isolated database."""
        if not self.sqlite_conn:
            self.init_database()

        adapter_factory = lambda *args, **kwargs: SQLitePyMySQLConnectionAdapter(self.sqlite_conn)

        # Import all models to ensure they are loaded in sys.modules
        import models.user
        import models.venue
        import models.event
        import models.fest
        import models.event_series
        import models.image
        import models.crowd_analysis
        import models.alert

        # Dynamically patch get_db_connection across all loaded modules (models, routes, tests)
        for mod_name, mod in list(sys.modules.items()):
            if mod and hasattr(mod, 'get_db_connection'):
                key = (id(mod), 'get_db_connection')
                if key not in self._original_conns:
                    self._original_conns[key] = (mod, 'get_db_connection', getattr(mod, 'get_db_connection', None))
                setattr(mod, 'get_db_connection', adapter_factory)

    def restore_models(self):
        """Restores original connection functions."""
        for key, (mod, attr, orig_func) in self._original_conns.items():
            if orig_func is not None:
                setattr(mod, attr, orig_func)
        self._original_conns.clear()
        if self.sqlite_conn:
            try:
                self.sqlite_conn.close()
            except Exception:
                pass
            self.sqlite_conn = None


# Auto-install safety guard on import of this module
install_global_safety_guard()
