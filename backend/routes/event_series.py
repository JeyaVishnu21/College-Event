"""
Compatibility module: re-exports fest_bp as event_series_bp and helper functions.
"""

from routes.fest import (
    fest_bp,
    event_series_bp,
    list_administrator_fests,
    list_management_event_series,
    create_administrator_fest,
    create_management_event_series,
    get_administrator_fest,
    get_management_event_series,
    update_administrator_fest,
    update_management_event_series,
    delete_administrator_fest,
    delete_management_event_series,
    serialize_data,
    serialize_field,
    validate_date_str
)

__all__ = [
    'fest_bp',
    'event_series_bp',
    'list_administrator_fests',
    'list_management_event_series',
    'create_administrator_fest',
    'create_management_event_series',
    'get_administrator_fest',
    'get_management_event_series',
    'update_administrator_fest',
    'update_management_event_series',
    'delete_administrator_fest',
    'delete_management_event_series'
]
