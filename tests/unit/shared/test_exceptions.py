"""Unit tests for the shared exception hierarchy."""

from shared.exceptions import (
    ClusterPulseError,
    ConfigurationError,
    FatalTransportError,
    RetryableTransportError,
    TransportError,
)


def test_cluster_pulse_error_carries_message_and_context() -> None:
    error = ClusterPulseError("boom", context={"node_id": "n1"})
    assert error.message == "boom"
    assert error.context == {"node_id": "n1"}
    assert str(error) == "boom"


def test_cluster_pulse_error_defaults_to_empty_context() -> None:
    error = ClusterPulseError("boom")
    assert error.context == {}


def test_configuration_error_is_a_cluster_pulse_error() -> None:
    assert isinstance(ConfigurationError("bad config"), ClusterPulseError)


def test_transport_error_hierarchy() -> None:
    assert issubclass(RetryableTransportError, TransportError)
    assert issubclass(FatalTransportError, TransportError)
    assert issubclass(TransportError, ClusterPulseError)
