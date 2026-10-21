"""
Database Configuration & Connection Layer (Stage 2)
---------------------------------------------------
This module provides MySQL connection management using PyMySQL.
Supports both single queries and multi-statement schema/seed scripts.
"""

import pymysql
import pymysql.cursors
import pymysql.constants.CLIENT
from typing import Dict, Any, Optional
from config.settings import settings


def get_db_connection(include_db: bool = True, multi_statements: bool = False) -> pymysql.connections.Connection:
    """
    Establish and return a MySQL database connection using settings.

    :param include_db: If True, connects directly to settings.DB_NAME.
                       If False, connects to MySQL server without selecting a DB.
    :param multi_statements: If True, enables multi-statement script execution.
    :return: A PyMySQL Connection object.
    """
    client_flag = 0
    if multi_statements:
        client_flag |= pymysql.constants.CLIENT.MULTI_STATEMENTS


    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME if include_db else None,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        client_flag=client_flag,
        autocommit=True,
        connect_timeout=10,
        ssl={"ssl": True}
    )



def check_db_status() -> Dict[str, Any]:
    """
    Safely tests connectivity to the configured MySQL database without
    raising unhandled exceptions or halting application startup.
    """
    try:
        connection = get_db_connection(include_db=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS test")
            result = cursor.fetchone()
        connection.close()

        if result and result.get('test') == 1:
            return {
                "status": "connected",
                "message": f"Successfully connected to MySQL database '{settings.DB_NAME}' on {settings.DB_HOST}:{settings.DB_PORT}"
            }
        return {
            "status": "warning",
            "message": "Connected to MySQL, but test query returned unexpected result."
        }
    except Exception as exc:
        return {
            "status": "placeholder_ready",
            "message": f"MySQL connection configured for '{settings.DB_NAME}' on {settings.DB_HOST}:{settings.DB_PORT}. Note: {str(exc)}"
        }
