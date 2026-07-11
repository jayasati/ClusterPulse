"""Transport-related exceptions.

Retryable vs. fatal is an explicit type distinction, not a flag, so the
retry policy in ``agent/transport/http_client.py`` can decide purely from
the exception type.
"""

from shared.exceptions.base import ClusterPulseError


class TransportError(ClusterPulseError):
    """Base class for errors raised while delivering data to the Collector."""


class RetryableTransportError(TransportError):
    """A transient failure (timeout, connection error, 5xx) worth retrying."""


class FatalTransportError(TransportError):
    """A non-retryable failure (4xx) — retrying the same payload will not help."""
