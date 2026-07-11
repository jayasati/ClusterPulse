"""SQLAlchemy-backed ``NodeRepository`` implementation."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from collector.db.models.node import NodeModel
from collector.db.timeutil import ensure_utc
from collector.repositories.protocols import NodeRecord
from shared.exceptions import PersistenceError


class SqlAlchemyNodeRepository:
    """Persists node registry rows via SQLAlchemy.

    Uses a get-then-write pattern (not a dialect-specific upsert) so the
    same code runs unmodified against PostgreSQL in production and SQLite
    in tests — see ``docs/adr/017-collector-sync-vs-async-db.md``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_seen(self, node_id: str, seen_at: datetime) -> NodeRecord:
        """Create the node on first sighting, or advance ``last_seen_at``."""
        try:
            node = self._session.get(NodeModel, node_id)
            if node is None:
                node = NodeModel(
                    node_id=node_id, first_seen_at=seen_at, last_seen_at=seen_at
                )
                self._session.add(node)
            else:
                node.last_seen_at = seen_at
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                "failed to record node heartbeat", context={"node_id": node_id}
            ) from exc
        return _to_record(node)

    def get(self, node_id: str) -> NodeRecord | None:
        """Return the node record for ``node_id``, or ``None`` if unknown."""
        try:
            node = self._session.get(NodeModel, node_id)
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to fetch node", context={"node_id": node_id}
            ) from exc
        return _to_record(node) if node is not None else None

    def list_all(self) -> list[NodeRecord]:
        """Return every known node record."""
        try:
            nodes = self._session.scalars(select(NodeModel)).all()
        except SQLAlchemyError as exc:
            raise PersistenceError("failed to list nodes") from exc
        return [_to_record(node) for node in nodes]


def _to_record(node: NodeModel) -> NodeRecord:
    return NodeRecord(
        node_id=node.node_id,
        first_seen_at=ensure_utc(node.first_seen_at),
        last_seen_at=ensure_utc(node.last_seen_at),
    )
