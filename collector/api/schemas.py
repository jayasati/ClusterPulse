"""The Collector's own read-API response models.

Distinct from ``shared.contracts`` — those are the Agent<->Collector wire
contract; these describe read-only views that only the Collector emits (no
Agent consumes them). See ``docs/architecture/00-project-initialization.md`` §9.
"""

from datetime import datetime

from pydantic import BaseModel

from collector.enums import AlertStatus, RuleKind
from collector.services.alerting import AlertView
from collector.services.node_registry import NodeView
from shared.constants import Severity


class NodeRead(BaseModel):
    """A single node registry entry, as returned by the read API."""

    node_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_stale: bool

    @classmethod
    def from_view(cls, view: NodeView) -> "NodeRead":
        """Build a ``NodeRead`` from a service-level ``NodeView``."""
        return cls(
            node_id=view.node_id,
            first_seen_at=view.first_seen_at,
            last_seen_at=view.last_seen_at,
            is_stale=view.is_stale,
        )


class AlertRead(BaseModel):
    """A single alert, as returned by the read API."""

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
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    escalated_at: datetime | None

    @classmethod
    def from_view(cls, view: AlertView) -> "AlertRead":
        """Build an ``AlertRead`` from a service-level ``AlertView``."""
        return cls(
            id=view.id,
            node_id=view.node_id,
            rule_key=view.rule_key,
            rule_kind=view.rule_kind,
            severity=view.severity,
            status=view.status,
            description=view.description,
            triggering_value=view.triggering_value,
            bound=view.bound,
            first_fired_at=view.first_fired_at,
            last_fired_at=view.last_fired_at,
            resolved_at=view.resolved_at,
            acknowledged_at=view.acknowledged_at,
            acknowledged_by=view.acknowledged_by,
            escalated_at=view.escalated_at,
        )


class AcknowledgeRequest(BaseModel):
    """Request body for ``POST /api/v1/alerts/{id}/acknowledge``."""

    acknowledged_by: str
