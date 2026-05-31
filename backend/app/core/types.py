"""
Custom SQLAlchemy types for cross-database compatibility
"""
import uuid
from sqlalchemy import TypeDecorator, String


class UUIDString(TypeDecorator):
    """
    Stores UUID as String(36) in the database.
    Automatically converts Python UUID objects to strings on bind,
    keeping results as strings for backward compatibility.
    """
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)
