"""Unit tests for RemediationActionService, using a fake repository."""

from datetime import datetime, timezone

import pytest

from collector.enums import RemediationActionStatus
from collector.exceptions import (
    RemediationActionNotDispatchedError,
    RemediationActionNotFoundError,
)
from collector.repositories.protocols import RemediationActionRecord
from collector.services.remediation import RemediationActionService
from shared.contracts.v1.remediation import (
    ActionResult,
    ActionResultStatus,
    PlaybookActionType,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeActionRepository:
    def __init__(self, actions=None) -> None:
        self._actions = {a.id: a for a in (actions or [])}

    def get(self, action_id):
        return self._actions.get(action_id)

    def list_actions(self, node_id=None):
        values = list(self._actions.values())
        if node_id is None:
            return values
        return [a for a in values if a.node_id == node_id]

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

    def create_action(self, **kwargs):  # pragma: no cover - unused by this service
        raise NotImplementedError

    def count_recent_actions(self, node_id, since):  # pragma: no cover - unused
        raise NotImplementedError

    def find_last_action(self, node_id, playbook_name):  # pragma: no cover - unused
        raise NotImplementedError


def _record(
    status: RemediationActionStatus, action_id: int = 1, node_id: str = "node-1"
) -> RemediationActionRecord:
    return RemediationActionRecord(
        id=action_id,
        node_id=node_id,
        alert_id=1,
        rule_key="threshold:disk.usage_percent",
        playbook_name="clear_tmp",
        action_type=PlaybookActionType.CLEAR_DIRECTORY,
        parameters={"path": "/tmp/reclaimable"},
        status=status,
        reason=None,
        created_at=_now(),
        completed_at=None,
    )


def test_get_action_returns_record() -> None:
    service = RemediationActionService(
        _FakeActionRepository([_record(RemediationActionStatus.DISPATCHED)])
    )
    assert service.get_action(1).id == 1


def test_get_action_raises_not_found() -> None:
    service = RemediationActionService(_FakeActionRepository())
    with pytest.raises(RemediationActionNotFoundError):
        service.get_action(999)


def test_list_actions_filters_by_node() -> None:
    service = RemediationActionService(
        _FakeActionRepository(
            [
                _record(RemediationActionStatus.DISPATCHED, action_id=1, node_id="a"),
                _record(RemediationActionStatus.DISPATCHED, action_id=2, node_id="b"),
            ]
        )
    )
    assert len(service.list_actions(node_id="a")) == 1
    assert len(service.list_actions()) == 2


def test_report_result_executed_updates_status() -> None:
    service = RemediationActionService(
        _FakeActionRepository([_record(RemediationActionStatus.DISPATCHED)])
    )

    updated = service.report_result(
        1, ActionResult(status=ActionResultStatus.EXECUTED, message="cleared 3")
    )

    assert updated.status == RemediationActionStatus.EXECUTED
    assert updated.reason == "cleared 3"
    assert updated.completed_at is not None


def test_report_result_failed_updates_status() -> None:
    service = RemediationActionService(
        _FakeActionRepository([_record(RemediationActionStatus.DISPATCHED)])
    )

    updated = service.report_result(
        1, ActionResult(status=ActionResultStatus.FAILED, message="permission denied")
    )

    assert updated.status == RemediationActionStatus.FAILED
    assert updated.reason == "permission denied"


def test_report_result_unknown_action_raises_not_found() -> None:
    service = RemediationActionService(_FakeActionRepository())
    with pytest.raises(RemediationActionNotFoundError):
        service.report_result(999, ActionResult(status=ActionResultStatus.EXECUTED))


def test_report_result_on_blocked_action_raises_not_dispatched() -> None:
    service = RemediationActionService(
        _FakeActionRepository(
            [_record(RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT)]
        )
    )
    with pytest.raises(RemediationActionNotDispatchedError):
        service.report_result(1, ActionResult(status=ActionResultStatus.EXECUTED))


def test_report_result_twice_raises_not_dispatched_the_second_time() -> None:
    service = RemediationActionService(
        _FakeActionRepository([_record(RemediationActionStatus.DISPATCHED)])
    )
    service.report_result(1, ActionResult(status=ActionResultStatus.EXECUTED))

    with pytest.raises(RemediationActionNotDispatchedError):
        service.report_result(1, ActionResult(status=ActionResultStatus.EXECUTED))
