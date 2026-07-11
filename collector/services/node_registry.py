"""Node registry business logic."""

from dataclasses import dataclass
from datetime import datetime, timezone

from collector.exceptions import NodeNotFoundError
from collector.repositories.protocols import NodeRecord, NodeRepository
from shared.constants import DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS


@dataclass(frozen=True)
class NodeView:
    """A node registry entry with staleness computed at read time."""

    node_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_stale: bool


class NodeRegistryService:
    """Tracks which nodes are known and whether they're still reporting in.

    Staleness is computed at read time from ``last_seen_at`` — there is no
    background sweep or alerting here; see
    ``docs/adr/003-heartbeat-deadman-switch.md``. Nodes are created lazily
    on first sighting; there is no separate registration step.
    """

    def __init__(
        self,
        repository: NodeRepository,
        stale_after_seconds: float = DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
    ) -> None:
        self._repository = repository
        self._stale_after_seconds = stale_after_seconds

    def record_seen(self, node_id: str, seen_at: datetime) -> NodeView:
        """Record that ``node_id`` was seen at ``seen_at``."""
        record = self._repository.upsert_seen(node_id, seen_at)
        return self._to_view(record)

    def get_node(self, node_id: str) -> NodeView:
        """Return ``node_id``'s registry entry, raising if it's unknown."""
        record = self._repository.get(node_id)
        if record is None:
            raise NodeNotFoundError(
                f"node {node_id!r} is not registered", context={"node_id": node_id}
            )
        return self._to_view(record)

    def list_nodes(self) -> list[NodeView]:
        """Return every known node's registry entry."""
        return [self._to_view(record) for record in self._repository.list_all()]

    def _to_view(self, record: NodeRecord) -> NodeView:
        age_seconds = (datetime.now(timezone.utc) - record.last_seen_at).total_seconds()
        return NodeView(
            node_id=record.node_id,
            first_seen_at=record.first_seen_at,
            last_seen_at=record.last_seen_at,
            is_stale=age_seconds > self._stale_after_seconds,
        )
