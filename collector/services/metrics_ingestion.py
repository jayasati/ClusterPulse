"""Metrics ingestion business logic."""

from datetime import datetime, timezone

from collector.repositories.protocols import MetricsRepository
from collector.services.node_registry import NodeRegistryService
from shared.contracts.v1.metrics import Ack, NodeMetricsPayload


class MetricsIngestionService:
    """Persists an incoming metrics payload and updates the node registry.

    Registry update happens before the metrics insert: ``metric_samples``
    has a foreign key on ``nodes.node_id``, so the node row must exist
    first — also true on a node's very first-ever push.
    """

    def __init__(
        self, metrics_repository: MetricsRepository, node_registry: NodeRegistryService
    ) -> None:
        self._metrics_repository = metrics_repository
        self._node_registry = node_registry

    def ingest(self, payload: NodeMetricsPayload) -> Ack:
        """Persist ``payload`` and return an acknowledgement."""
        received_at = datetime.now(timezone.utc)
        self._node_registry.record_seen(payload.node_id, seen_at=payload.collected_at)
        self._metrics_repository.bulk_insert(
            node_id=payload.node_id,
            samples=payload.samples,
            collected_at=payload.collected_at,
            received_at=received_at,
        )
        return Ack(accepted=True, received_at=received_at)
