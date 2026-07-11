"""Repository interfaces (PEP 544 Protocols) and their plain-data records.

Records are plain ``dataclasses``, not SQLAlchemy ORM instances — services
and routes depend only on these, never on ``collector.db.models`` directly,
so a repository's storage details stay fully encapsulated.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

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
