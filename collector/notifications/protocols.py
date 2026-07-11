"""Notification delivery interface."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """Something that can deliver a human-readable alert message.

    Implementations must never raise — notification delivery is
    best-effort and must never affect alert-state persistence or the
    Agent-facing ingestion contract (``collector/services/metrics_ingestion.py``
    already isolates the whole rule-evaluation step, but well-behaved
    notifiers shouldn't rely on that outer safety net). The returned
    ``bool`` is for logging/testing only — callers are not required to
    act on it.
    """

    def notify(self, message: str) -> bool:
        """Attempt to deliver ``message``. Returns whether it succeeded."""
        ...
