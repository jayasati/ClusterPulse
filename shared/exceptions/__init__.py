"""The ClusterPulse exception hierarchy.

Application code raises one of these explicit types — never a bare stdlib
exception — so error handling at process boundaries can rely on a single
root type (``ClusterPulseError``) and structured ``context`` for logging.
See ``docs/architecture/00-project-initialization.md`` §7.
"""

from shared.exceptions.auth import AuthenticationError
from shared.exceptions.base import ClusterPulseError
from shared.exceptions.config import ConfigurationError
from shared.exceptions.persistence import PersistenceError
from shared.exceptions.transport import (
    FatalTransportError,
    RetryableTransportError,
    TransportError,
)

__all__ = [
    "ClusterPulseError",
    "ConfigurationError",
    "AuthenticationError",
    "PersistenceError",
    "TransportError",
    "RetryableTransportError",
    "FatalTransportError",
]
