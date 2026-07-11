"""Unit tests for SqlAlchemyAlertRepository."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from collector.enums import AlertStatus, RuleKind
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from shared.constants import Severity
from shared.exceptions import PersistenceError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_node(db_session, node_id: str = "node-1") -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen(node_id, _now())


def _create(
    repo: SqlAlchemyAlertRepository,
    node_id: str = "node-1",
    rule_key: str = "threshold:cpu.usage_percent",
):
    return repo.create_alert(
        node_id=node_id,
        rule_key=rule_key,
        rule_kind=RuleKind.THRESHOLD,
        severity=Severity.CRITICAL,
        description="CPU too high",
        triggering_value=95.0,
        bound=90.0,
        fired_at=_now(),
    )


def test_create_alert_starts_firing(db_session) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)

    record = _create(repo)

    assert record.status == AlertStatus.FIRING
    assert record.first_fired_at == record.last_fired_at
    assert record.resolved_at is None


def test_find_open_alert_returns_firing_alert(db_session) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    created = _create(repo)

    found = repo.find_open_alert("node-1", "threshold:cpu.usage_percent")

    assert found is not None
    assert found.id == created.id


def test_find_open_alert_returns_none_when_no_open_alert(db_session) -> None:
    repo = SqlAlchemyAlertRepository(db_session)
    assert repo.find_open_alert("node-1", "threshold:cpu.usage_percent") is None


def test_update_last_fired_advances_without_creating_new_row(db_session) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    created = _create(repo)
    later = _now()

    updated = repo.update_last_fired(created.id, triggering_value=99.0, fired_at=later)

    assert updated.id == created.id
    assert updated.triggering_value == 99.0
    assert updated.last_fired_at == later
    assert updated.first_fired_at == created.first_fired_at
    assert len(repo.list_alerts()) == 1


def test_resolve_alert_transitions_status(db_session) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    created = _create(repo)
    resolved_at = _now()

    resolved = repo.resolve_alert(created.id, resolved_at=resolved_at)

    assert resolved.status == AlertStatus.RESOLVED
    assert resolved.resolved_at == resolved_at
    assert repo.find_open_alert("node-1", "threshold:cpu.usage_percent") is None


def test_get_returns_none_for_unknown_alert(db_session) -> None:
    repo = SqlAlchemyAlertRepository(db_session)
    assert repo.get(999) is None


def test_list_alerts_filters_by_status(db_session) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    firing = _create(repo, rule_key="threshold:cpu.usage_percent")
    to_resolve = _create(repo, rule_key="threshold:memory.usage_percent")
    repo.resolve_alert(to_resolve.id, resolved_at=_now())

    firing_only = repo.list_alerts(status=AlertStatus.FIRING)
    resolved_only = repo.list_alerts(status=AlertStatus.RESOLVED)

    assert [a.id for a in firing_only] == [firing.id]
    assert [a.id for a in resolved_only] == [to_resolve.id]
    assert len(repo.list_alerts()) == 2


def test_records_are_timezone_aware_even_from_sqlite(db_session) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    created = _create(repo)

    fetched = repo.get(created.id)

    assert fetched is not None
    assert fetched.first_fired_at.tzinfo is not None
    assert fetched.last_fired_at.tzinfo is not None


def test_create_alert_wraps_db_errors_as_persistence_error(
    db_session, monkeypatch
) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    monkeypatch.setattr(
        db_session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError("boom"))
    )

    with pytest.raises(PersistenceError):
        _create(repo)


def test_update_last_fired_raises_when_alert_missing(db_session) -> None:
    repo = SqlAlchemyAlertRepository(db_session)

    with pytest.raises(PersistenceError):
        repo.update_last_fired(999, triggering_value=1.0, fired_at=_now())


def test_resolve_alert_raises_when_alert_missing(db_session) -> None:
    repo = SqlAlchemyAlertRepository(db_session)

    with pytest.raises(PersistenceError):
        repo.resolve_alert(999, resolved_at=_now())


def test_update_last_fired_wraps_session_get_error(db_session, monkeypatch) -> None:
    repo = SqlAlchemyAlertRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.update_last_fired(1, triggering_value=1.0, fired_at=_now())


def test_update_last_fired_wraps_commit_error(db_session, monkeypatch) -> None:
    _ensure_node(db_session)
    repo = SqlAlchemyAlertRepository(db_session)
    created = _create(repo)
    monkeypatch.setattr(
        db_session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError("boom"))
    )

    with pytest.raises(PersistenceError):
        repo.update_last_fired(created.id, triggering_value=1.0, fired_at=_now())


def test_find_open_alert_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyAlertRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "scalars",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.find_open_alert("node-1", "threshold:cpu.usage_percent")


def test_get_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyAlertRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.get(1)


def test_list_alerts_wraps_db_errors(db_session, monkeypatch) -> None:
    repo = SqlAlchemyAlertRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "scalars",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.list_alerts()
