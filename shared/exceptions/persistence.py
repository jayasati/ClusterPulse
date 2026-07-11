"""Persistence-related exceptions."""

from shared.exceptions.base import ClusterPulseError


class PersistenceError(ClusterPulseError):
    """Raised when a database operation fails unexpectedly.

    Repositories wrap the underlying driver/ORM exception in this type so
    callers (API error handlers, services) never need to know about
    SQLAlchemy specifically — see ``docs/adr/017-collector-sync-vs-async-db.md``.
    """
