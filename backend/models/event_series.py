"""
Compatibility module: imports and re-exports FestModel as EventSeriesModel.
"""

from models.fest import FestModel, EventSeriesModel

__all__ = ['FestModel', 'EventSeriesModel']
