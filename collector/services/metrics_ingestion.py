"""Metrics ingestion business logic."""

from datetime import datetime, timezone

import structlog

from collector.repositories.protocols import MetricsRepository
from collector.services.alerting import AlertEvaluationService
from collector.services.node_registry import NodeRegistryService
from shared.contracts.v1.metrics import Ack, NodeMetricsPayload

logger = structlog.get_logger(__name__)


class MetricsIngestionService:
    """Persists an incoming metrics payload and updates the node registry.

    Registry update happens before the metrics insert: ``metric_samples``
    has a foreign key on ``nodes.node_id``, so the node row must exist
    first — also true on a node's very first-ever push.
    """

    def __init__(
        self,
        metrics_repository: MetricsRepository,
        node_registry: NodeRegistryService,
        alert_evaluation: AlertEvaluationService | None = None,
    ) -> None:
        self._metrics_repository = metrics_repository
        self._node_registry = node_registry
        self._alert_evaluation = alert_evaluation

    def ingest(self, payload: NodeMetricsPayload) -> Ack:
        """Persist ``payload``, evaluate rules, and return an acknowledgement.

        Rule evaluation is best-effort: a failure there is logged and
        swallowed, never surfaced as a failed ingestion — the Agent's
        retry/buffer behavior must not be triggered by a Rule Engine bug
        when the metrics themselves were persisted successfully.
        """
        received_at = datetime.now(timezone.utc)
        self._node_registry.record_seen(payload.node_id, seen_at=payload.collected_at)
        self._metrics_repository.bulk_insert(
            node_id=payload.node_id,
            samples=payload.samples,
            collected_at=payload.collected_at,
            received_at=received_at,
        )
        self._evaluate_rules_best_effort(payload)
        return Ack(accepted=True, received_at=received_at)

    def _evaluate_rules_best_effort(self, payload: NodeMetricsPayload) -> None:
        if self._alert_evaluation is None:
            return
        try:
            self._alert_evaluation.evaluate_and_apply(
                payload.node_id, payload.samples, payload.collected_at
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 - a Rule Engine bug must never fail ingestion
            logger.error(
                "rule_evaluation_failed", node_id=payload.node_id, error=str(exc)
            )
