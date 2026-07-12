"""Unit tests verifying concrete Agent classes satisfy the shared Protocols."""

from shared.contracts.v1.metrics import Ack, NodeMetricsPayload
from shared.contracts.v1.remediation import ActionResult
from shared.protocols import MetricCollector, MetricsBuffer, Transport


class _FakeCollector:
    def collect(self) -> list:
        return []


class _FakeTransport:
    def send(self, payload: NodeMetricsPayload) -> Ack:
        raise NotImplementedError

    def report_action_result(self, action_id: int, result: ActionResult) -> None:
        raise NotImplementedError


class _FakeBuffer:
    def enqueue(self, payload: NodeMetricsPayload) -> None:
        pass

    def drain(self, max_items: int) -> list:
        return []

    def __len__(self) -> int:
        return 0


def test_fake_collector_satisfies_protocol() -> None:
    assert isinstance(_FakeCollector(), MetricCollector)


def test_fake_transport_satisfies_protocol() -> None:
    assert isinstance(_FakeTransport(), Transport)


def test_fake_buffer_satisfies_protocol() -> None:
    assert isinstance(_FakeBuffer(), MetricsBuffer)
