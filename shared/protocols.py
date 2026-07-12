"""Structural interfaces (PEP 544 Protocols) shared across ClusterPulse.

Protocols are used instead of abstract base classes so concrete
implementations satisfy an interface by shape alone — composition over
inheritance, per ``.claude/CODING_STANDARDS.md`` — with no coupling to a
shared base class.
"""

from typing import Protocol, runtime_checkable

from shared.contracts.v1.metrics import Ack, MetricSample, NodeMetricsPayload
from shared.contracts.v1.remediation import ActionResult


@runtime_checkable
class MetricCollector(Protocol):
    """Something that can produce a batch of metric samples for the local node."""

    def collect(self) -> list[MetricSample]:
        """Return the current metric samples for this collector's domain."""
        ...


@runtime_checkable
class Transport(Protocol):
    """Something that can deliver a metrics payload to the Collector."""

    def send(self, payload: NodeMetricsPayload) -> Ack:
        """Deliver ``payload`` to the Collector and return its acknowledgement."""
        ...

    def report_action_result(self, action_id: int, result: ActionResult) -> None:
        """Report the outcome of executing a dispatched remediation action."""
        ...


@runtime_checkable
class MetricsBuffer(Protocol):
    """Durable local storage for payloads that could not be delivered immediately."""

    def enqueue(self, payload: NodeMetricsPayload) -> None:
        """Persist ``payload`` for later delivery."""
        ...

    def drain(self, max_items: int) -> list[NodeMetricsPayload]:
        """Remove and return up to ``max_items`` buffered payloads, oldest first."""
        ...

    def __len__(self) -> int:
        """Return the number of currently buffered payloads."""
        ...
