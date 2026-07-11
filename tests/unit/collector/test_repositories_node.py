"""Unit tests for SqlAlchemyNodeRepository."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from collector.repositories.node_repository import SqlAlchemyNodeRepository
from shared.exceptions import PersistenceError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_upsert_seen_creates_new_node(db_session) -> None:
    repo = SqlAlchemyNodeRepository(db_session)
    seen_at = _now()

    record = repo.upsert_seen("node-1", seen_at)

    assert record.node_id == "node-1"
    assert record.first_seen_at == seen_at
    assert record.last_seen_at == seen_at


def test_upsert_seen_advances_last_seen_without_changing_first_seen(db_session) -> None:
    repo = SqlAlchemyNodeRepository(db_session)
    first_seen = _now()
    repo.upsert_seen("node-1", first_seen)

    later = first_seen + timedelta(minutes=5)
    record = repo.upsert_seen("node-1", later)

    assert record.first_seen_at == first_seen
    assert record.last_seen_at == later


def test_get_returns_none_for_unknown_node(db_session) -> None:
    repo = SqlAlchemyNodeRepository(db_session)
    assert repo.get("does-not-exist") is None


def test_get_returns_the_record(db_session) -> None:
    repo = SqlAlchemyNodeRepository(db_session)
    seen_at = _now()
    repo.upsert_seen("node-1", seen_at)

    record = repo.get("node-1")

    assert record is not None
    assert record.node_id == "node-1"


def test_list_all_returns_every_node(db_session) -> None:
    repo = SqlAlchemyNodeRepository(db_session)
    repo.upsert_seen("node-1", _now())
    repo.upsert_seen("node-2", _now())

    records = repo.list_all()

    assert {r.node_id for r in records} == {"node-1", "node-2"}


def test_records_are_timezone_aware_even_from_sqlite(db_session) -> None:
    """Guards against the SQLite naive-datetime round-trip gotcha."""
    repo = SqlAlchemyNodeRepository(db_session)
    repo.upsert_seen("node-1", _now())

    record = repo.get("node-1")

    assert record is not None
    assert record.first_seen_at.tzinfo is not None
    assert record.last_seen_at.tzinfo is not None


def test_upsert_seen_wraps_db_errors_as_persistence_error(
    db_session, monkeypatch
) -> None:
    repo = SqlAlchemyNodeRepository(db_session)

    def _raise(*args, **kwargs):
        raise SQLAlchemyError("connection lost")

    monkeypatch.setattr(db_session, "commit", _raise)

    with pytest.raises(PersistenceError):
        repo.upsert_seen("node-1", _now())


def test_get_wraps_db_errors_as_persistence_error(db_session, monkeypatch) -> None:
    repo = SqlAlchemyNodeRepository(db_session)

    def _raise(*args, **kwargs):
        raise SQLAlchemyError("connection lost")

    monkeypatch.setattr(db_session, "get", _raise)

    with pytest.raises(PersistenceError):
        repo.get("node-1")


def test_list_all_wraps_db_errors_as_persistence_error(db_session, monkeypatch) -> None:
    repo = SqlAlchemyNodeRepository(db_session)

    def _raise(*args, **kwargs):
        raise SQLAlchemyError("connection lost")

    monkeypatch.setattr(db_session, "scalars", _raise)

    with pytest.raises(PersistenceError):
        repo.list_all()
