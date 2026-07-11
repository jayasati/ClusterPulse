"""Configuration-related exceptions."""

from shared.exceptions.base import ClusterPulseError


class ConfigurationError(ClusterPulseError):
    """Raised when service configuration fails to load or validate.

    Callers are expected to let this propagate and abort startup — no
    component should proceed with partially-valid configuration.
    """
