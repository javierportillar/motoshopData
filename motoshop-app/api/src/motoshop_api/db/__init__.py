"""Capa de acceso a datos (SQLAlchemy core)."""

from motoshop_api.db.engine import get_engine
from motoshop_api.db.tables import metadata

__all__ = ["get_engine", "metadata"]
