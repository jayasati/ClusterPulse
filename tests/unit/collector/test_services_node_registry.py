"""Unit tests for NodeRegistryService, using a fake NodeRepository."""

from datetime import datetime, timedelta, timezone

import pytest

from collector.exceptions import NodeNotFoundError
from collector.repositories.protocols import NodeRecord
from collector.services.node_registry import NodeRegistryService


class _FakeNodeRepository:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeRecord] = {}

    def upsert_seen(self, node_id: str, seen_at: datetime) -> NodeRecord:
        existing = self._nodes.get(node_id)
        first_seen = existing.first_seen_at if existing else seen_at
        record = NodeRecord(
            node_id=node_id, first_seen_at=first_seen, last_seen_at=seen_at
        )
        self._nodes[node_id] = record
        return record

    def get(self, node_id: str) -> NodeRecord | None:
        return self._nodes.get(node_id)

    def list_all(self) -> list[NodeRecord]:
        return list(self._nodes.values())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_record_seen_creates_view() -> None:
    service = NodeRegistryService(_FakeNodeRepository())

    view = service.record_seen("node-1", _now())

    assert view.node_id == "node-1"
    assert view.is_stale is False


def test_get_node_raises_not_found_for_unknown_node() -> None:
    service = NodeRegistryService(_FakeNodeRepository())

    with pytest.raises(NodeNotFoundError):
        service.get_node("missing")


def test_get_node_marks_stale_past_threshold() -> None:
    repo = _FakeNodeRepository()
    service = NodeRegistryService(repo, stale_after_seconds=60)
    repo.upsert_seen("node-1", _now() - timedelta(seconds=120))

    view = service.get_node("node-1")

    assert view.is_stale is True


def test_get_node_not_stale_within_threshold() -> None:
    repo = _FakeNodeRepository()
    service = NodeRegistryService(repo, stale_after_seconds=600)
    repo.upsert_seen("node-1", _now() - timedelta(seconds=5))

    view = service.get_node("node-1")

    assert view.is_stale is False


def test_upsert_seen_preserves_first_seen_across_calls() -> None:
    repo = _FakeNodeRepository()
    service = NodeRegistryService(repo)
    first_seen = _now() - timedelta(hours=1)
    service.record_seen("node-1", first_seen)

    view = service.record_seen("node-1", _now())

    assert view.first_seen_at == first_seen


def test_list_nodes_returns_all() -> None:
    repo = _FakeNodeRepository()
    service = NodeRegistryService(repo)
    repo.upsert_seen("node-1", _now())
    repo.upsert_seen("node-2", _now())

    views = service.list_nodes()

    assert {v.node_id for v in views} == {"node-1", "node-2"}
