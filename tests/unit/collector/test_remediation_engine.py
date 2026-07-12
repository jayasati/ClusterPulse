"""Unit tests for RemediationEngine, using a fake RemediationActionRepository."""

from datetime import datetime, timedelta, timezone

from collector.enums import RemediationActionStatus
from collector.remediation.definitions import PlaybookDefinition, RemediationPolicy
from collector.remediation.engine import RemediationEngine
from collector.repositories.protocols import RemediationActionRecord
from shared.contracts.v1.remediation import PlaybookActionType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeActionRepository:
    def __init__(self) -> None:
        self._actions: dict[int, RemediationActionRecord] = {}
        self._next_id = 1

    def create_action(
        self,
        node_id,
        alert_id,
        rule_key,
        playbook_name,
        action_type,
        parameters,
        status,
        reason,
        created_at,
    ):
        record = RemediationActionRecord(
            id=self._next_id,
            node_id=node_id,
            alert_id=alert_id,
            rule_key=rule_key,
            playbook_name=playbook_name,
            action_type=action_type,
            parameters=parameters,
            status=status,
            reason=reason,
            created_at=created_at,
            completed_at=None,
        )
        self._actions[self._next_id] = record
        self._next_id += 1
        return record

    def mark_result(self, action_id, status, reason, completed_at):
        record = self._actions[action_id]
        updated = RemediationActionRecord(
            **{
                **record.__dict__,
                "status": status,
                "reason": reason,
                "completed_at": completed_at,
            }
        )
        self._actions[action_id] = updated
        return updated

    def count_recent_actions(self, node_id, since):
        return sum(
            1
            for a in self._actions.values()
            if a.node_id == node_id and a.created_at >= since
        )

    def find_last_action(self, node_id, playbook_name):
        candidates = [
            a
            for a in self._actions.values()
            if a.node_id == node_id and a.playbook_name == playbook_name
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda a: a.created_at)

    def get(self, action_id):
        return self._actions.get(action_id)

    def list_actions(self, node_id=None):
        values = list(self._actions.values())
        if node_id is None:
            return values
        return [a for a in values if a.node_id == node_id]


def _policy(rule_key: str = "threshold:disk.usage_percent") -> RemediationPolicy:
    return RemediationPolicy(
        playbooks=[
            PlaybookDefinition(
                rule_key=rule_key,
                playbook_name="clear_tmp",
                action_type=PlaybookActionType.CLEAR_DIRECTORY,
                parameters={"path": "/tmp/reclaimable"},
                description="Clear reclaimable temp space",
            )
        ]
    )


def _engine(
    repository=None, enabled=True, max_per_hour=3, cooldown_seconds=1800.0
) -> RemediationEngine:
    return RemediationEngine(
        _policy(),
        repository if repository is not None else _FakeActionRepository(),
        enabled=enabled,
        max_actions_per_node_per_hour=max_per_hour,
        cooldown_seconds=cooldown_seconds,
    )


def test_disabled_engine_returns_none_and_records_nothing() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo, enabled=False)

    decision = engine.decide("node-1", 1, "threshold:disk.usage_percent", _now())

    assert decision is None
    assert repo.list_actions() == []


def test_no_playbook_mapped_returns_none_and_records_nothing() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo)

    decision = engine.decide("node-1", 1, "threshold:cpu.usage_percent", _now())

    assert decision is None
    assert repo.list_actions() == []


def test_mapped_playbook_dispatches_and_is_recorded() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo)

    decision = engine.decide("node-1", 1, "threshold:disk.usage_percent", _now())

    assert decision is not None
    assert decision.status == RemediationActionStatus.DISPATCHED
    assert decision.playbook_name == "clear_tmp"
    assert decision.parameters == {"path": "/tmp/reclaimable"}
    assert len(repo.list_actions()) == 1


def test_rate_limit_blocks_after_max_reached() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo, max_per_hour=1, cooldown_seconds=0.0)
    now = _now()
    first = engine.decide("node-1", 1, "threshold:disk.usage_percent", now)
    assert first.status == RemediationActionStatus.DISPATCHED

    second = engine.decide(
        "node-1", 2, "threshold:disk.usage_percent", now + timedelta(seconds=1)
    )

    assert second.status == RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT
    assert second.reason is not None


def test_cooldown_blocks_before_it_elapses() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo, max_per_hour=10, cooldown_seconds=1800.0)
    now = _now()
    engine.decide("node-1", 1, "threshold:disk.usage_percent", now)

    soon = now + timedelta(seconds=60)
    second = engine.decide("node-1", 2, "threshold:disk.usage_percent", soon)

    assert second.status == RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT


def test_cooldown_allows_dispatch_once_elapsed() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo, max_per_hour=10, cooldown_seconds=60.0)
    now = _now()
    engine.decide("node-1", 1, "threshold:disk.usage_percent", now)

    later = now + timedelta(seconds=61)
    second = engine.decide("node-1", 2, "threshold:disk.usage_percent", later)

    assert second.status == RemediationActionStatus.DISPATCHED


def test_different_nodes_have_independent_safety_limits() -> None:
    repo = _FakeActionRepository()
    engine = _engine(repository=repo, max_per_hour=1, cooldown_seconds=1800.0)
    now = _now()
    engine.decide("node-1", 1, "threshold:disk.usage_percent", now)

    other_node = engine.decide("node-2", 2, "threshold:disk.usage_percent", now)

    assert other_node.status == RemediationActionStatus.DISPATCHED
