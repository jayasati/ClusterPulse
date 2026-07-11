"""The Collector's own read-API response models.

Distinct from ``shared.contracts`` — those are the Agent<->Collector wire
contract; these describe a read-only registry view that only the Collector
emits (no Agent consumes it in Phase 2). See
``docs/architecture/00-project-initialization.md`` §9.
"""

from datetime import datetime

from pydantic import BaseModel

from collector.services.node_registry import NodeView


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
