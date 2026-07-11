"""Datetime normalization helpers shared by repository implementations."""

from datetime import datetime, timezone


def ensure_utc(value: datetime) -> datetime:
    """Normalize a naive datetime to UTC-aware.

    SQLite (used in tests) does not reliably round-trip timezone-aware
    ``DateTime`` columns and can hand back a naive value even though only
    UTC-aware values are ever written. PostgreSQL preserves tzinfo
    correctly, so this is a no-op there.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
