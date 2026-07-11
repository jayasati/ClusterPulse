"""Applies rule-evaluation results to the Alert Lifecycle state machine."""

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from collector.enums import AlertStatus, RuleKind
from collector.exceptions import AlertAlreadyResolvedError, AlertNotFoundError
from collector.notifications import formatting
from collector.notifications.protocols import Notifier
from collector.repositories.protocols import AlertRecord, AlertRepository
from collector.rules.engine import RuleEngine, RuleEvaluationResult
from shared.constants import DEFAULT_ESCALATION_AFTER_SECONDS, Severity
from shared.contracts.v1.metrics import MetricSample

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AlertView:
    """An alert, decoupled from the repository/ORM layer.

    ``acknowledged_at``/``acknowledged_by``/``escalated_at`` default to
    ``None`` so Phase 3 call sites keep working unmodified.
    """

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
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    escalated_at: datetime | None = None


class AlertEvaluationService:
    """Applies the Alert Lifecycle (firing -> resolved) from rule results.

    A breach with no existing open alert opens one; a still-breaching
    evaluation advances the existing alert's ``last_fired_at`` (this is
    the Phase 3 dedup — "don't open a duplicate row for an already-firing
    condition"); a no-longer-breaching evaluation resolves the open alert.

    Phase 4 adds: acknowledgement (suppresses escalation on a firing
    alert), single-tier escalation (checked opportunistically each time a
    still-firing alert advances — there is no scheduler, so an alert only
    escalates while its node keeps pushing), and best-effort notification
    on state *transitions* only (opened/escalated/resolved — never on the
    unchanged "still firing" advance, which is the Phase 4
    notification-level dedup). See ``docs/adr/006-alert-lifecycle.md``,
    ``docs/adr/019-alert-acknowledgement-escalation.md``.
    """

    def __init__(
        self,
        rule_engine: RuleEngine,
        alert_repository: AlertRepository,
        notifier: Notifier | None = None,
        escalation_after_seconds: float = DEFAULT_ESCALATION_AFTER_SECONDS,
    ) -> None:
        self._rule_engine = rule_engine
        self._alert_repository = alert_repository
        self._notifier = notifier
        self._escalation_after_seconds = escalation_after_seconds

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

    def acknowledge(self, alert_id: int, acknowledged_by: str) -> AlertView:
        """Acknowledge a firing alert, suppressing further escalation.

        Idempotent while firing (re-acknowledging just updates who/when —
        e.g. a shift handoff). Raises ``AlertAlreadyResolvedError`` if the
        alert has already resolved; there's nothing left to acknowledge.
        """
        current = self.get_alert(alert_id)
        if current.status == AlertStatus.RESOLVED:
            raise AlertAlreadyResolvedError(
                f"alert {alert_id!r} is already resolved",
                context={"alert_id": alert_id},
            )
        updated = self._alert_repository.acknowledge_alert(
            alert_id,
            acknowledged_by=acknowledged_by,
            acknowledged_at=datetime.now(timezone.utc),
        )
        return _to_view(updated)

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
            return _to_view(self._resolve(node_id, result, fired_at, open_alert))
        return None

    def _open_or_advance(
        self,
        node_id: str,
        result: RuleEvaluationResult,
        fired_at: datetime,
        open_alert: AlertRecord | None,
    ) -> AlertRecord:
        if open_alert is None:
            return self._open(node_id, result, fired_at)
        advanced = self._alert_repository.update_last_fired(
            open_alert.id, triggering_value=result.value, fired_at=fired_at
        )
        return self._maybe_escalate(node_id, result, fired_at, advanced)

    def _open(
        self, node_id: str, result: RuleEvaluationResult, fired_at: datetime
    ) -> AlertRecord:
        record = self._alert_repository.create_alert(
            node_id=node_id,
            rule_key=result.rule_key,
            rule_kind=result.rule_kind,
            severity=result.severity,
            description=result.description,
            triggering_value=result.value,
            bound=result.bound,
            fired_at=fired_at,
        )
        logger.warning(
            "alert_opened",
            node_id=node_id,
            rule_key=result.rule_key,
            severity=result.severity.value,
            value=result.value,
        )
        self._notify(formatting.format_opened(record))
        return record

    def _maybe_escalate(
        self,
        node_id: str,
        result: RuleEvaluationResult,
        fired_at: datetime,
        record: AlertRecord,
    ) -> AlertRecord:
        if not self._should_escalate(record, fired_at):
            return record
        escalated = self._alert_repository.escalate_alert(
            record.id, escalated_at=fired_at
        )
        logger.warning("alert_escalated", node_id=node_id, rule_key=result.rule_key)
        self._notify(formatting.format_escalated(escalated))
        return escalated

    def _should_escalate(self, record: AlertRecord, now: datetime) -> bool:
        if record.acknowledged_at is not None or record.escalated_at is not None:
            return False
        age_seconds = (now - record.first_fired_at).total_seconds()
        return age_seconds >= self._escalation_after_seconds

    def _resolve(
        self,
        node_id: str,
        result: RuleEvaluationResult,
        resolved_at: datetime,
        open_alert: AlertRecord,
    ) -> AlertRecord:
        record = self._alert_repository.resolve_alert(
            open_alert.id, resolved_at=resolved_at
        )
        logger.info("alert_resolved", node_id=node_id, rule_key=result.rule_key)
        self._notify(formatting.format_resolved(record))
        return record

    def _notify(self, message: str) -> None:
        if self._notifier is not None:
            self._notifier.notify(message)


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
        acknowledged_at=record.acknowledged_at,
        acknowledged_by=record.acknowledged_by,
        escalated_at=record.escalated_at,
    )
