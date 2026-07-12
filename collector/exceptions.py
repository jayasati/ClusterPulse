"""Collector-local domain exceptions.

Unlike ``shared.exceptions`` (generic, cross-service concerns), these are
specific to the Collector's own domain model and have no reason to be
imported by the Agent.
"""

from shared.exceptions import ClusterPulseError


class NodeNotFoundError(ClusterPulseError):
    """Raised when a requested node is not present in the registry."""


class AlertNotFoundError(ClusterPulseError):
    """Raised when a requested alert does not exist."""


class AlertAlreadyResolvedError(ClusterPulseError):
    """Raised when acknowledgement is attempted on a resolved alert."""


class RemediationActionNotFoundError(ClusterPulseError):
    """Raised when a requested remediation action does not exist."""


class RemediationActionNotDispatchedError(ClusterPulseError):
    """Raised when a result is reported for an action that isn't ``DISPATCHED``.

    A result only makes sense for an action the Collector actually sent to
    an Agent — reporting one for an action that was blocked by a Safety
    Limit, or that already has a result, is a caller bug, not a retryable
    condition.
    """
