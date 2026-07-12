"""The Agent -> Collector metrics wire contract (v1).

Both Agent and Collector import these exact classes — there is exactly one
definition of the wire format. See
``docs/architecture/00-project-initialization.md`` §9 for why this lives in
``shared`` rather than being duplicated per side.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from shared.constants import MetricType
from shared.contracts.v1.remediation import PendingAction


class MetricSample(BaseModel):
    """A single metric observation produced by one Agent collector."""

    metric_type: MetricType
    value: float
    unit: str
    labels: dict[str, str] = Field(default_factory=dict)


class NodeMetricsPayload(BaseModel):
    """Everything one Agent collection cycle pushes to the Collector."""

    node_id: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    samples: list[MetricSample] = Field(default_factory=list)
    collection_errors: list[str] = Field(default_factory=list)


class Ack(BaseModel):
    """The Collector's acknowledgement of a received payload.

    ``pending_actions`` rides this same response rather than a separate
    poll — remediation decisions are made synchronously during this same
    ingestion request, so there is nothing to gain from a second round
    trip. Defaults to empty, so this is a backward-compatible wire change.
    """

    accepted: bool
    received_at: datetime
    message: str | None = None
    pending_actions: list[PendingAction] = Field(default_factory=list)
