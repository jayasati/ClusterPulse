"""The declarative base every ORM model inherits from.

Kept in its own module (rather than alongside a model) so both
``collector/db/models/*`` and ``collector/db/migrations/env.py`` (Alembic
autogenerate) can import it without a circular dependency.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all Collector ORM models."""
