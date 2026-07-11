"""Applies rule-evaluation results to the Alert Lifecycle state machine."""

from dataclasses import dataclass
from datetime import datetime

import structlog

from collector.enums import AlertStatus, RuleKind
from collector.exceptions import AlertNotFoundError
from collector.repositories.protocols import AlertRecord, AlertRepository
from collector.rules.engine import RuleEngine, RuleEvaluationResult
from shared.constants import Severity
from shared.contracts.v1.metrics import MetricSample

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AlertView:
    """An alert, decoupled from the repository/ORM layer."""

    id: int
    node_id: str
    rule_key: str
    rule_kind: RuleKind
    severity: Severity
    status: AlertStatus
    description: str
    triggering_value: float
    bound: float
    first_fired_at: datetime
    last_fired_at: datetime
    resolved_at: datetime | None


class AlertEvaluationService:
    """Applies the Alert Lifecycle (firing -> resolved) from rule results.

    A breach with no existing open alert opens one; a still-breaching
    evaluation advances the existing alert's ``last_fired_at`` (this is
    the Phase 3 dedup — "don't open a duplicate row for an already-firing
    condition" — distinct from Phase 4's notification-level dedup); a
    no-longer-breaching evaluation resolves the open alert. Also serves
    read access to alerts, mirroring how ``NodeRegistryService`` covers
    both writes and reads for the node registry. See
    ``docs/adr/006-alert-lifecycle.md``.
    """

    def __init__(
        self, rule_engine: RuleEngine, alert_repository: AlertRepository
    ) -> None:
        self._rule_engine = rule_engine
        self._alert_repository = alert_repository

    def get_alert(self, alert_id: int) -> AlertView:
        """Return the alert with ``alert_id``, raising if it doesn't exist."""
        record = self._alert_repository.get(alert_id)
        if record is None:
            raise AlertNotFoundError(
                f"alert {alert_id!r} does not exist", context={"alert_id": alert_id}
            )
        return _to_view(record)

    def list_alerts(self, status: AlertStatus | None = None) -> list[AlertView]:
        """Return every alert, optionally filtered to a single ``status``."""
        return [
            _to_view(record) for record in self._alert_repository.list_alerts(status)
        ]

    def evaluate_and_apply(
        self, node_id: str, samples: list[MetricSample], collected_at: datetime
    ) -> list[AlertView]:
        """Evaluate configured rules and apply any resulting alert transitions."""
        results = self._rule_engine.evaluate(node_id, samples, collected_at)
        transitions: list[AlertView] = []
        for result in results:
            transition = self._apply(node_id, result, collected_at)
            if transition is not None:
                transitions.append(transition)
        return transitions

    def _apply(
        self, node_id: str, result: RuleEvaluationResult, fired_at: datetime
    ) -> AlertView | None:
        open_alert = self._alert_repository.find_open_alert(node_id, result.rule_key)
        if result.breached:
            return _to_view(
                self._open_or_advance(node_id, result, fired_at, open_alert)
            )
        if open_alert is not None:
            record = self._alert_repository.resolve_alert(
                open_alert.id, resolved_at=fired_at
            )
            logger.info("alert_resolved", node_id=node_id, rule_key=result.rule_key)
            return _to_view(record)
        return None

    def _open_or_advance(
        self,
        node_id: str,
        result: RuleEvaluationResult,
        fired_at: datetime,
        open_alert: AlertRecord | None,
    ) -> AlertRecord:
        if open_alert is None:
            logger.warning(
                "alert_opened",
                node_id=node_id,
                rule_key=result.rule_key,
                severity=result.severity.value,
                value=result.value,
            )
            return self._alert_repository.create_alert(
                node_id=node_id,
                rule_key=result.rule_key,
                rule_kind=result.rule_kind,
                severity=result.severity,
                description=result.description,
                triggering_value=result.value,
                bound=result.bound,
                fired_at=fired_at,
            )
        return self._alert_repository.update_last_fired(
            open_alert.id, triggering_value=result.value, fired_at=fired_at
        )


def _to_view(record: AlertRecord) -> AlertView:
    return AlertView(
        id=record.id,
        node_id=record.node_id,
        rule_key=record.rule_key,
        rule_kind=record.rule_kind,
        severity=record.severity,
        status=record.status,
        description=record.description,
        triggering_value=record.triggering_value,
        bound=record.bound,
        first_fired_at=record.first_fired_at,
        last_fired_at=record.last_fired_at,
        resolved_at=record.resolved_at,
    )
