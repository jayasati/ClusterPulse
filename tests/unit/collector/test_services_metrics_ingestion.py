"""Unit tests for MetricsIngestionService, using fakes for both repositories."""

from datetime import datetime, timezone

from collector.repositories.protocols import NodeRecord
from collector.services.metrics_ingestion import MetricsIngestionService
from collector.services.node_registry import NodeRegistryService
from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample, NodeMetricsPayload


def _payload() -> NodeMetricsPayload:
    return NodeMetricsPayload(
        node_id="node-1",
        collected_at=datetime.now(timezone.utc),
        samples=[
            MetricSample(
                metric_type=MetricType.CPU_USAGE_PERCENT, value=1.0, unit="percent"
            )
        ],
    )


def test_ingest_returns_accepted_ack() -> None:
    class _NodeRepo:
        def upsert_seen(self, node_id, seen_at):
            return NodeRecord(
                node_id=node_id, first_seen_at=seen_at, last_seen_at=seen_at
            )

        def get(self, node_id):
            return None

        def list_all(self):
            return []

    class _MetricsRepo:
        def bulk_insert(self, node_id, samples, collected_at, received_at):
            pass

    service = MetricsIngestionService(_MetricsRepo(), NodeRegistryService(_NodeRepo()))

    ack = service.ingest(_payload())

    assert ack.accepted is True


def test_ingest_records_registry_before_persisting_metrics() -> None:
    """The node row must exist before the metrics insert (FK dependency)."""
    call_order: list[str] = []

    class _NodeRepo:
        def upsert_seen(self, node_id, seen_at):
            call_order.append("node")
            return NodeRecord(
                node_id=node_id, first_seen_at=seen_at, last_seen_at=seen_at
            )

        def get(self, node_id):
            return None

        def list_all(self):
            return []

    class _MetricsRepo:
        def bulk_insert(self, node_id, samples, collected_at, received_at):
            call_order.append("metrics")

    service = MetricsIngestionService(_MetricsRepo(), NodeRegistryService(_NodeRepo()))

    service.ingest(_payload())

    assert call_order == ["node", "metrics"]


def test_ingest_uses_payload_collected_at_for_both_repositories() -> None:
    captured = {}

    class _NodeRepo:
        def upsert_seen(self, node_id, seen_at):
            captured["node_seen_at"] = seen_at
            return NodeRecord(
                node_id=node_id, first_seen_at=seen_at, last_seen_at=seen_at
            )

        def get(self, node_id):
            return None

        def list_all(self):
            return []

    class _MetricsRepo:
        def bulk_insert(self, node_id, samples, collected_at, received_at):
            captured["metrics_collected_at"] = collected_at

    service = MetricsIngestionService(_MetricsRepo(), NodeRegistryService(_NodeRepo()))
    payload = _payload()

    service.ingest(payload)

    assert captured["node_seen_at"] == payload.collected_at
    assert captured["metrics_collected_at"] == payload.collected_at


class _NodeRepo:
    def upsert_seen(self, node_id, seen_at):
        return NodeRecord(node_id=node_id, first_seen_at=seen_at, last_seen_at=seen_at)

    def get(self, node_id):
        return None

    def list_all(self):
        return []


class _MetricsRepo:
    def bulk_insert(self, node_id, samples, collected_at, received_at):
        pass


def test_ingest_invokes_alert_evaluation_when_provided() -> None:
    calls = []

    class _FakeAlertEvaluation:
        def evaluate_and_apply(self, node_id, samples, collected_at):
            calls.append((node_id, samples, collected_at))
            return []

    service = MetricsIngestionService(
        _MetricsRepo(), NodeRegistryService(_NodeRepo()), _FakeAlertEvaluation()
    )
    payload = _payload()

    ack = service.ingest(payload)

    assert ack.accepted is True
    assert calls == [(payload.node_id, payload.samples, payload.collected_at)]


def test_ingest_works_without_alert_evaluation_collaborator() -> None:
    """Backward compatibility: the collaborator is optional."""
    service = MetricsIngestionService(_MetricsRepo(), NodeRegistryService(_NodeRepo()))

    ack = service.ingest(_payload())

    assert ack.accepted is True


def test_alert_evaluation_failure_is_logged_and_does_not_fail_ingestion() -> None:
    from shared.exceptions import PersistenceError

    class _FailingAlertEvaluation:
        def evaluate_and_apply(self, node_id, samples, collected_at):
            raise PersistenceError("db exploded")

    service = MetricsIngestionService(
        _MetricsRepo(), NodeRegistryService(_NodeRepo()), _FailingAlertEvaluation()
    )

    ack = service.ingest(_payload())  # must not raise

    assert ack.accepted is True


def test_alert_evaluation_unexpected_exception_does_not_fail_ingestion() -> None:
    """Not just ClusterPulseError — a genuine Rule Engine bug (AttributeError,
    TypeError, etc.) must not fail ingestion either."""

    class _BuggyAlertEvaluation:
        def evaluate_and_apply(self, node_id, samples, collected_at):
            raise RuntimeError("unexpected bug")

    service = MetricsIngestionService(
        _MetricsRepo(), NodeRegistryService(_NodeRepo()), _BuggyAlertEvaluation()
    )

    ack = service.ingest(_payload())  # must not raise

    assert ack.accepted is True
