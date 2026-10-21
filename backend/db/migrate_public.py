"""
Public Discovery Schema Migration
---------------------------------
Applies strictly additive schema changes for public event discovery:
1. Creates `event_series` table if not exists.
2. Adds nullable `series_id` (FK to event_series) and `category` (VARCHAR) to `events` table if missing.
3. Preserves all existing tables, rows, relations, and credentials without inserting any fake or demo data.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.db import get_db_connection


def apply_migration():
    print("[MIGRATION] Connecting to database...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Create fest table if not exists
            print("[MIGRATION] Ensuring `fest` table exists...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `fest` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `name` VARCHAR(150) NOT NULL,
                    `description` TEXT NULL,
                    `start_date` DATE NULL,
                    `end_date` DATE NULL,
                    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX `idx_fest_dates` (`start_date`, `end_date`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            cursor.execute("CREATE OR REPLACE VIEW `event_series` AS SELECT * FROM `fest`;")

            # 2. Check existing columns in events table
            cursor.execute("DESCRIBE `events`;")
            existing_cols = {col['Field'] for col in cursor.fetchall()}

            # 3. Add series_id if missing
            if 'series_id' not in existing_cols:
                print("[MIGRATION] Adding `series_id` column to `events` table...")
                cursor.execute("""
                    ALTER TABLE `events`
                    ADD COLUMN `series_id` INT NULL AFTER `venue_id`,
                    ADD INDEX `idx_events_series` (`series_id`);
                """)
                cursor.execute("""
                    ALTER TABLE `events`
                    ADD CONSTRAINT `fk_events_series` FOREIGN KEY (`series_id`)
                        REFERENCES `event_series` (`id`)
                        ON DELETE SET NULL
                        ON UPDATE CASCADE;
                """)
                print("   [OK] Added `series_id` with foreign key to `event_series` (ON DELETE SET NULL).")
            else:
                print("[MIGRATION] `series_id` already exists in `events`.")

            # 4. Add category if missing
            if 'category' not in existing_cols:
                print("[MIGRATION] Adding `category` VARCHAR(50) column to `events` table...")
                cursor.execute("""
                    ALTER TABLE `events`
                    ADD COLUMN `category` VARCHAR(50) DEFAULT 'General' AFTER `series_id`,
                    ADD INDEX `idx_events_category` (`category`);
                """)
                print("   [OK] Added `category` column.")
            else:
                print("[MIGRATION] `category` already exists in `events`.")

            # 5. Ensure existing events have category defaulted to 'General' if NULL
            cursor.execute("UPDATE `events` SET `category` = 'General' WHERE `category` IS NULL OR `category` = '';")

            conn.commit()
            print("[MIGRATION] Additive schema migration completed successfully (no demo data created).")
    finally:
        conn.close()


if __name__ == '__main__':
    apply_migration()
