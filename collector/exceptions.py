"""Collector-local domain exceptions.

Unlike ``shared.exceptions`` (generic, cross-service concerns), these are
specific to the Collector's own domain model and have no reason to be
imported by the Agent.
"""

from shared.exceptions import ClusterPulseError


class NodeNotFoundError(ClusterPulseError):
    """Raised when a requested node is not present in the registry."""
