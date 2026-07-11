"""Root of the ClusterPulse exception hierarchy."""

from typing import Any


class ClusterPulseError(Exception):
    """Base class for every explicit, application-raised ClusterPulse error.

    Carries a structured ``context`` dict alongside the message so the
    logging layer can log the failure as structured fields rather than
    parsing them back out of a message string.
    """

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context or {}
