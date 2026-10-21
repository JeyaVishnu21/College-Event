"""
Data Models Package (Stage 2)
-----------------------------
Provides structured, beginner-friendly database access abstractions
for all entities in the Crowd Event Management System.
"""

from models.user import UserModel
from models.venue import VenueModel
from models.event import EventModel
from models.image import ImageModel
from models.crowd_analysis import CrowdAnalysisModel
from models.alert import AlertModel
from models.fest import FestModel, EventSeriesModel

__all__ = [
    'UserModel',
    'VenueModel',
    'EventModel',
    'ImageModel',
    'CrowdAnalysisModel',
    'AlertModel',
    'FestModel',
    'EventSeriesModel'
]
