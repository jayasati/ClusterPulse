"""Authentication-related exceptions."""

from shared.exceptions.base import ClusterPulseError


class AuthenticationError(ClusterPulseError):
    """Raised when a request's credentials are missing or invalid.

    A generic, cross-service concern (any service accepting inbound
    requests may need it) — currently only the Collector raises it.
    """
