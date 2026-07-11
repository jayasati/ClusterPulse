"""The Agent -> Collector heartbeat wire contract (v1).

A lighter-weight liveness signal than a full ``NodeMetricsPayload`` — see
``docs/adr/003-heartbeat-deadman-switch.md``. The response reuses
``shared.contracts.v1.metrics.Ack``; there is no need for a second,
differently-shaped acknowledgement.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class HeartbeatPing(BaseModel):
    """A minimal liveness signal from one Agent."""

    node_id: str
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
