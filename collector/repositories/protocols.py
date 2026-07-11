"""Repository interfaces (PEP 544 Protocols) and their plain-data records.

Records are plain ``dataclasses``, not SQLAlchemy ORM instances — services
and routes depend only on these, never on ``collector.db.models`` directly,
so a repository's storage details stay fully encapsulated.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from collector.enums import AlertStatus, RuleKind
from shared.constants import MetricType, Severity
from shared.contracts.v1.metrics import MetricSample


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
    """A persisted alert, decoupled from the ORM model that stores it."""

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

    def get(self, alert_id: int) -> AlertRecord | None:
        """Return the alert with ``alert_id``, or ``None`` if unknown."""
        ...

    def list_alerts(self, status: AlertStatus | None = None) -> list[AlertRecord]:
        """Return every alert, optionally filtered to a single ``status``."""
        ...
