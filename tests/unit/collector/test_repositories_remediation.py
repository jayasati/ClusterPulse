"""Unit tests for SqlAlchemyRemediationActionRepository."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from collector.enums import RemediationActionStatus
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from collector.repositories.remediation_repository import (
    SqlAlchemyRemediationActionRepository,
)
from shared.contracts.v1.remediation import PlaybookActionType
from shared.exceptions import PersistenceError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_node_and_alert(db_session, node_id: str = "node-1") -> int:
    SqlAlchemyNodeRepository(db_session).upsert_seen(node_id, _now())
    from collector.enums import RuleKind
    from shared.constants import Severity

    alert = SqlAlchemyAlertRepository(db_session).create_alert(
        node_id=node_id,
        rule_key="threshold:disk.usage_percent",
        rule_kind=RuleKind.THRESHOLD,
        severity=Severity.WARNING,
        description="disk too full",
        triggering_value=95.0,
        bound=85.0,
        fired_at=_now(),
    )
    return alert.id


def _create(
    repo: SqlAlchemyRemediationActionRepository,
    node_id: str,
    alert_id: int,
    playbook_name: str = "clear_tmp",
    status: RemediationActionStatus = RemediationActionStatus.DISPATCHED,
    created_at: datetime | None = None,
):
    return repo.create_action(
        node_id=node_id,
        alert_id=alert_id,
        rule_key="threshold:disk.usage_percent",
        playbook_name=playbook_name,
        action_type=PlaybookActionType.CLEAR_DIRECTORY,
        parameters={"path": "/tmp/reclaimable"},
        status=status,
        reason=None,
        created_at=created_at or _now(),
    )


def test_create_action_persists_dispatched_status(db_session) -> None:
    alert_id = _ensure_node_and_alert(db_session)
    repo = SqlAlchemyRemediationActionRepository(db_session)

    record = _create(repo, "node-1", alert_id)

    assert record.status == RemediationActionStatus.DISPATCHED
    assert record.completed_at is None
    assert record.parameters == {"path": "/tmp/reclaimable"}


def test_mark_result_sets_status_reason_and_completed_at(db_session) -> None:
    alert_id = _ensure_node_and_alert(db_session)
    repo = SqlAlchemyRemediationActionRepository(db_session)
    created = _create(repo, "node-1", alert_id)
    completed_at = _now()

    updated = repo.mark_result(
        created.id,
        status=RemediationActionStatus.EXECUTED,
        reason="cleared 3 entries",
        completed_at=completed_at,
    )

    assert updated.status == RemediationActionStatus.EXECUTED
    assert updated.reason == "cleared 3 entries"
    assert updated.completed_at == completed_at


def test_mark_result_raises_when_action_missing(db_session) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)

    with pytest.raises(PersistenceError):
        repo.mark_result(
            999,
            status=RemediationActionStatus.EXECUTED,
            reason=None,
            completed_at=_now(),
        )


def test_count_recent_actions_counts_only_since_cutoff(db_session) -> None:
    alert_id = _ensure_node_and_alert(db_session)
    repo = SqlAlchemyRemediationActionRepository(db_session)
    now = _now()
    _create(repo, "node-1", alert_id, created_at=now - timedelta(hours=2))
    _create(repo, "node-1", alert_id, created_at=now - timedelta(minutes=10))

    count = repo.count_recent_actions("node-1", since=now - timedelta(hours=1))

    assert count == 1


def test_count_recent_actions_is_scoped_to_node(db_session) -> None:
    alert_id = _ensure_node_and_alert(db_session, "node-1")
    other_alert_id = _ensure_node_and_alert(db_session, "node-2")
    repo = SqlAlchemyRemediationActionRepository(db_session)
    now = _now()
    _create(repo, "node-1", alert_id, created_at=now)
    _create(repo, "node-2", other_alert_id, created_at=now)

    count = repo.count_recent_actions("node-1", since=now - timedelta(hours=1))

    assert count == 1


def test_find_last_action_returns_most_recent_for_node_and_playbook(db_session) -> None:
    alert_id = _ensure_node_and_alert(db_session)
    repo = SqlAlchemyRemediationActionRepository(db_session)
    now = _now()
    _create(repo, "node-1", alert_id, created_at=now - timedelta(minutes=30))
    latest = _create(repo, "node-1", alert_id, created_at=now)

    found = repo.find_last_action("node-1", "clear_tmp")

    assert found is not None
    assert found.id == latest.id


def test_find_last_action_returns_none_when_no_match(db_session) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    assert repo.find_last_action("node-1", "clear_tmp") is None


def test_get_returns_none_for_unknown_action(db_session) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    assert repo.get(999) is None


def test_list_actions_filters_by_node(db_session) -> None:
    alert_id = _ensure_node_and_alert(db_session, "node-1")
    other_alert_id = _ensure_node_and_alert(db_session, "node-2")
    repo = SqlAlchemyRemediationActionRepository(db_session)
    _create(repo, "node-1", alert_id)
    _create(repo, "node-2", other_alert_id)

    assert len(repo.list_actions(node_id="node-1")) == 1
    assert len(repo.list_actions()) == 2


def test_create_action_wraps_db_errors(db_session, monkeypatch) -> None:
    alert_id = _ensure_node_and_alert(db_session)
    repo = SqlAlchemyRemediationActionRepository(db_session)
    monkeypatch.setattr(
        db_session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError("boom"))
    )

    with pytest.raises(PersistenceError):
        _create(repo, "node-1", alert_id)


def test_mark_result_wraps_commit_error(db_session, monkeypatch) -> None:
    alert_id = _ensure_node_and_alert(db_session)
    repo = SqlAlchemyRemediationActionRepository(db_session)
    created = _create(repo, "node-1", alert_id)
    monkeypatch.setattr(
        db_session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError("boom"))
    )

    with pytest.raises(PersistenceError):
        repo.mark_result(
            created.id,
            status=RemediationActionStatus.EXECUTED,
            reason=None,
            completed_at=_now(),
        )


def test_mark_result_wraps_session_get_error(db_session, monkeypatch) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.mark_result(
            1, status=RemediationActionStatus.EXECUTED, reason=None, completed_at=_now()
        )


def test_count_recent_actions_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "scalar",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.count_recent_actions("node-1", since=_now())


def test_find_last_action_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "scalars",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.find_last_action("node-1", "clear_tmp")


def test_get_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.get(1)


def test_list_actions_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyRemediationActionRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "scalars",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.list_actions()
