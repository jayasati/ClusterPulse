"""Applies rule-evaluation results to the Alert Lifecycle state machine."""

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from collector.enums import AlertStatus, RemediationActionStatus, RuleKind
from collector.exceptions import AlertAlreadyResolvedError, AlertNotFoundError
from collector.notifications import formatting
from collector.notifications.protocols import Notifier
from collector.remediation.engine import RemediationEngine
from collector.repositories.protocols import (
    AlertRecord,
    AlertRepository,
    RemediationActionRecord,
)
from collector.rules.engine import RuleEngine, RuleEvaluationResult
from shared.constants import (
    DEFAULT_ESCALATION_AFTER_SECONDS,
    DEFAULT_REMEDIATION_AFTER_SECONDS,
    Severity,
)
from shared.contracts.v1.metrics import MetricSample

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AlertView:
    """An alert, decoupled from the repository/ORM layer.

    ``acknowledged_at``/``acknowledged_by``/``escalated_at``/``remediated_at``
    default to ``None`` so call sites that predate a given field keep
    working unmodified.
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
    remediated_at: datetime | None = None


@dataclass(frozen=True)
class EvaluationOutcome:
    """The result of evaluating one ingestion cycle's samples.

    ``dispatched_actions`` are remediation decisions that were actually
    ``DISPATCHED`` (never ``BLOCKED_BY_SAFETY_LIMIT`` ones — those stay in
    the audit log only) — the caller (``MetricsIngestionService``) turns
    these into ``PendingAction`` wire objects carried on the ``Ack``.
    """

    transitions: list[AlertView]
    dispatched_actions: list[RemediationActionRecord]


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

    Phase 5 adds: remediation, considered at the same opportunistic
    "still-firing advance" point as escalation, gated on its own
    ``remediation_after_seconds`` (validated >= ``escalation_after_seconds``
    at config load — a human always gets a chance first) and attempted at
    most once per alert, whether the ``RemediationEngine`` ends up
    dispatching a Playbook or blocking it on a Safety Limit. See
    ``docs/adr/007-remediation-safety.md``.
    """

    def __init__(
        self,
        rule_engine: RuleEngine,
        alert_repository: AlertRepository,
        notifier: Notifier | None = None,
        escalation_after_seconds: float = DEFAULT_ESCALATION_AFTER_SECONDS,
        remediation_engine: RemediationEngine | None = None,
        remediation_after_seconds: float = DEFAULT_REMEDIATION_AFTER_SECONDS,
    ) -> None:
        self._rule_engine = rule_engine
        self._alert_repository = alert_repository
        self._notifier = notifier
        self._escalation_after_seconds = escalation_after_seconds
        self._remediation_engine = remediation_engine
        self._remediation_after_seconds = remediation_after_seconds

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
    ) -> EvaluationOutcome:
        """Evaluate configured rules and apply any resulting alert transitions."""
        results = self._rule_engine.evaluate(node_id, samples, collected_at)
        transitions: list[AlertView] = []
        dispatched_actions: list[RemediationActionRecord] = []
        for result in results:
            view, dispatched = self._apply(node_id, result, collected_at)
            if view is not None:
                transitions.append(view)
            if dispatched is not None:
                dispatched_actions.append(dispatched)
        return EvaluationOutcome(
            transitions=transitions, dispatched_actions=dispatched_actions
        )

    def _apply(
        self, node_id: str, result: RuleEvaluationResult, fired_at: datetime
    ) -> tuple[AlertView | None, RemediationActionRecord | None]:
        open_alert = self._alert_repository.find_open_alert(node_id, result.rule_key)
        if result.breached:
            record, dispatched = self._open_or_advance(
                node_id, result, fired_at, open_alert
            )
            return _to_view(record), dispatched
        if open_alert is not None:
            resolved = self._resolve(node_id, result, fired_at, open_alert)
            return _to_view(resolved), None
        return None, None

    def _open_or_advance(
        self,
        node_id: str,
        result: RuleEvaluationResult,
        fired_at: datetime,
        open_alert: AlertRecord | None,
    ) -> tuple[AlertRecord, RemediationActionRecord | None]:
        if open_alert is None:
            return self._open(node_id, result, fired_at), None
        advanced = self._alert_repository.update_last_fired(
            open_alert.id, triggering_value=result.value, fired_at=fired_at
        )
        escalated = self._maybe_escalate(node_id, result, fired_at, advanced)
        return self._maybe_remediate(node_id, result, fired_at, escalated)

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

    def _maybe_remediate(
        self,
        node_id: str,
        result: RuleEvaluationResult,
        fired_at: datetime,
        record: AlertRecord,
    ) -> tuple[AlertRecord, RemediationActionRecord | None]:
        if not self._should_remediate(record, fired_at):
            return record, None
        assert self._remediation_engine is not None  # guarded by _should_remediate
        decision = self._remediation_engine.decide(
            node_id, record.id, result.rule_key, fired_at
        )
        if decision is None:
            # Remediation disabled, or no Playbook mapped to this rule_key —
            # nothing happened, so don't consume the one-shot attempt: a
            # Playbook added later while this alert is still firing should
            # still get a chance.
            return record, None
        updated = self._alert_repository.mark_remediated(
            record.id, remediated_at=fired_at
        )
        dispatched = (
            decision if decision.status == RemediationActionStatus.DISPATCHED else None
        )
        return updated, dispatched

    def _should_remediate(self, record: AlertRecord, now: datetime) -> bool:
        if self._remediation_engine is None:
            return False
        if record.acknowledged_at is not None or record.remediated_at is not None:
            return False
        age_seconds = (now - record.first_fired_at).total_seconds()
        return age_seconds >= self._remediation_after_seconds

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
        remediated_at=record.remediated_at,
    )
