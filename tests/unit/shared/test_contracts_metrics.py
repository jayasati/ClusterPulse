"""Unit tests for the v1 metrics wire contract."""

from datetime import datetime, timezone

from shared.constants import MetricType
from shared.contracts.v1.metrics import Ack, MetricSample, NodeMetricsPayload


def test_metric_sample_defaults_labels_to_empty_dict() -> None:
    sample = MetricSample(
        metric_type=MetricType.CPU_USAGE_PERCENT, value=1.0, unit="percent"
    )
    assert sample.labels == {}


def test_node_metrics_payload_round_trips_through_json() -> None:
    payload = NodeMetricsPayload(
        node_id="node-1",
        samples=[
            MetricSample(
                metric_type=MetricType.CPU_USAGE_PERCENT, value=42.0, unit="percent"
            )
        ],
    )
    restored = NodeMetricsPayload.model_validate_json(payload.model_dump_json())
    assert restored == payload


def test_node_metrics_payload_defaults_to_empty_samples_and_errors() -> None:
    payload = NodeMetricsPayload(node_id="node-1")
    assert payload.samples == []
    assert payload.collection_errors == []


def test_ack_requires_received_at() -> None:
    ack = Ack(accepted=True, received_at=datetime.now(timezone.utc))
    assert ack.accepted is True
    assert ack.message is None
