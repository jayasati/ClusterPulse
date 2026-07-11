"""Helper for mapping ``(str, Enum)`` classes to SQLAlchemy columns correctly.

SQLAlchemy's ``Enum(SomeEnumClass)`` defaults to storing each member's
``.name`` (e.g. ``"CPU_USAGE_PERCENT"``), not its ``.value`` (e.g.
``"cpu.usage_percent"``) — a well-known gotcha. Every Alembic migration in
this project defines the Postgres enum type's labels from the members'
``.value`` (see e.g. ``_METRIC_TYPE_VALUES`` in
``collector/db/migrations/versions/0001_initial_schema.py``), so every
enum-typed column must be built through this helper to match, or inserts
fail against a real Postgres with ``invalid input value for enum`` —
SQLite's test schema doesn't catch this, since ``Base.metadata.create_all()``
derives its own CHECK constraint from the same (otherwise-mismatched)
default, making the bug self-consistent and invisible until tested against
a real migration-created Postgres database.
"""

from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SqlEnum

_EnumT = TypeVar("_EnumT", bound=Enum)


def str_enum_column(enum_cls: type[_EnumT]) -> SqlEnum:
    """Build a ``sqlalchemy.Enum`` that stores ``enum_cls`` members by value."""
    return SqlEnum(
        enum_cls, values_callable=lambda cls: [member.value for member in cls]
    )
