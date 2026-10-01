"""Local workspace persistence; normalized application data only."""

from backend.storage.database import Database, initialize_database

__all__ = ["Database", "initialize_database"]
