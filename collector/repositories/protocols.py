"""Repository interfaces (PEP 544 Protocols) and their plain-data records.

Records are plain ``dataclasses``, not SQLAlchemy ORM instances — services
and routes depend only on these, never on ``collector.db.models`` directly,
so a repository's storage details stay fully encapsulated.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from collector.enums import AlertStatus, RemediationActionStatus, RuleKind
from shared.constants import MetricType, Severity
from shared.contracts.v1.metrics import MetricSample
from shared.contracts.v1.remediation import PlaybookActionType


@dataclass(frozen=True)
class NodeRecord:
    """A node registry row, decoupled from the ORM model that stores it."""

    node_id: str
    first_seen_at: datetime
    last_seen_at: datetime


class NodeRepository(Protocol):
    """Storage for the node registry."""

    def upsert_seen(self, node_id: str, seen_at: datetime) -> NodeRecord:
        """Record that ``node_id`` was seen at ``seen_at``.

        Creates the node (with ``first_seen_at == seen_at``) if it doesn't
        exist yet, or advances ``last_seen_at`` if it does.
        """
        ...

    def get(self, node_id: str) -> NodeRecord | None:
        """Return the node record for ``node_id``, or ``None`` if unknown."""
        ...

    def list_all(self) -> list[NodeRecord]:
        """Return every known node record."""
        ...


@dataclass(frozen=True)
class MetricSampleRecord:
    """A persisted metric sample, decoupled from the ORM model that stores it."""

    node_id: str
    metric_type: MetricType
    value: float
    unit: str
    labels: dict[str, str]
    collected_at: datetime
    received_at: datetime


class MetricsRepository(Protocol):
    """Storage for ingested metric samples."""

    def bulk_insert(
        self,
        node_id: str,
        samples: list[MetricSample],
        collected_at: datetime,
        received_at: datetime,
    ) -> None:
        """Persist every sample in ``samples`` for ``node_id``."""
        ...

    def find_previous_sample(
        self,
        node_id: str,
        metric_type: MetricType,
        before: datetime,
        window_seconds: float,
    ) -> MetricSampleRecord | None:
        """Return the most recent sample for ``node_id``/``metric_type`` that
        was collected strictly before ``before`` and no earlier than
        ``window_seconds`` before it — or ``None`` if there isn't one.

        Used by rate-of-change rules (``collector/rules/engine.py``); a
        comparison against a sample older than the configured window would
        be meaningless, so the window bound is enforced here, not by the
        caller.
        """
        ...


@dataclass(frozen=True)
class AlertRecord:
    """A persisted alert, decoupled from the ORM model that stores it.

    ``acknowledged_at``/``acknowledged_by``/``escalated_at``/``remediated_at``
    default to ``None`` so existing construction call sites that predate a
    given field keep working unmodified.
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


class AlertRepository(Protocol):
    """Storage for alerts and their lifecycle transitions."""

    def find_open_alert(self, node_id: str, rule_key: str) -> AlertRecord | None:
        """Return the currently-firing alert for ``(node_id, rule_key)``, if any."""
        ...

    def create_alert(
        self,
        node_id: str,
        rule_key: str,
        rule_kind: RuleKind,
        severity: Severity,
        description: str,
        triggering_value: float,
        bound: float,
        fired_at: datetime,
    ) -> AlertRecord:
        """Open a new alert in the ``firing`` state."""
        ...

    def update_last_fired(
        self, alert_id: int, triggering_value: float, fired_at: datetime
    ) -> AlertRecord:
        """Advance an already-firing alert's ``last_fired_at``/``triggering_value``."""
        ...

    def resolve_alert(self, alert_id: int, resolved_at: datetime) -> AlertRecord:
        """Transition an alert from ``firing`` to ``resolved``."""
        ...

    def acknowledge_alert(
        self, alert_id: int, acknowledged_by: str, acknowledged_at: datetime
    ) -> AlertRecord:
        """Set acknowledgement info on an alert. Idempotent while firing."""
        ...

    def escalate_alert(self, alert_id: int, escalated_at: datetime) -> AlertRecord:
        """Mark an alert as escalated. Callers ensure this happens at most once."""
        ...

    def mark_remediated(self, alert_id: int, remediated_at: datetime) -> AlertRecord:
        """Mark an alert as having had a remediation decision made for it.

        Set regardless of whether the decision was dispatched or blocked by
        a Safety Limit — either way, this alert gets at most one
        remediation attempt (mirrors escalation's single-tier pattern).
        Callers ensure this happens at most once.
        """
        ...

    def get(self, alert_id: int) -> AlertRecord | None:
        """Return the alert with ``alert_id``, or ``None`` if unknown."""
        ...

    def list_alerts(self, status: AlertStatus | None = None) -> list[AlertRecord]:
        """Return every alert, optionally filtered to a single ``status``."""
        ...


@dataclass(frozen=True)
class RemediationActionRecord:
    """A persisted remediation decision, decoupled from the ORM model that stores it.

    ``reason`` holds the safety-limit-blocked explanation or the Agent's
    failure message; ``None`` for a successful dispatch/execution.
    ``completed_at`` is set once the Agent reports a result (``EXECUTED``/
    ``FAILED``) — ``None`` while still ``DISPATCHED``, or for a decision
    that never left ``BLOCKED_BY_SAFETY_LIMIT``.
    """

    id: int
    node_id: str
    alert_id: int
    rule_key: str
    playbook_name: str
    action_type: PlaybookActionType
    parameters: dict[str, str]
    status: RemediationActionStatus
    reason: str | None
    created_at: datetime
    completed_at: datetime | None


class RemediationActionRepository(Protocol):
    """Storage for remediation decisions — the Playbook audit log."""

    def create_action(
        self,
        node_id: str,
        alert_id: int,
        rule_key: str,
        playbook_name: str,
        action_type: PlaybookActionType,
        parameters: dict[str, str],
        status: RemediationActionStatus,
        reason: str | None,
        created_at: datetime,
    ) -> RemediationActionRecord:
        """Record a new remediation decision (dispatched or safety-blocked)."""
        ...

    def mark_result(
        self,
        action_id: int,
        status: RemediationActionStatus,
        reason: str | None,
        completed_at: datetime,
    ) -> RemediationActionRecord:
        """Record the Agent-reported terminal outcome of a dispatched action."""
        ...

    def count_recent_actions(self, node_id: str, since: datetime) -> int:
        """Count actions created for ``node_id`` at or after ``since`` (any status).

        Used for the per-node-per-hour rate limit.
        """
        ...

    def find_last_action(
        self, node_id: str, playbook_name: str
    ) -> RemediationActionRecord | None:
        """Return the most recently created action for ``(node_id, playbook_name)``.

        Used for the cooldown-since-last-action safety limit.
        """
        ...

    def get(self, action_id: int) -> RemediationActionRecord | None:
        """Return the action with ``action_id``, or ``None`` if unknown."""
        ...

    def list_actions(self, node_id: str | None = None) -> list[RemediationActionRecord]:
        """Return every recorded action, optionally filtered to one ``node_id``."""
        ...
