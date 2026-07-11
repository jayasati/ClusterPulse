"""Unit tests for SqlAlchemyMetricsRepository."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from collector.db.models.metric_sample import MetricSampleModel
from collector.repositories.metrics_repository import SqlAlchemyMetricsRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample
from shared.exceptions import PersistenceError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sample() -> MetricSample:
    return MetricSample(
        metric_type=MetricType.CPU_USAGE_PERCENT,
        value=12.5,
        unit="percent",
        labels={"mount_point": "/"},
    )


def test_bulk_insert_persists_every_sample(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)
    collected_at = _now()

    repo.bulk_insert(
        node_id="node-1",
        samples=[_sample(), _sample()],
        collected_at=collected_at,
        received_at=_now(),
    )

    rows = db_session.scalars(select(MetricSampleModel)).all()
    assert len(rows) == 2
    assert all(row.node_id == "node-1" for row in rows)
    assert all(row.labels == {"mount_point": "/"} for row in rows)


def test_bulk_insert_with_empty_samples_is_a_no_op(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)

    repo.bulk_insert(
        node_id="node-1", samples=[], collected_at=_now(), received_at=_now()
    )

    assert db_session.scalars(select(MetricSampleModel)).all() == []


def test_bulk_insert_for_unknown_node_raises_persistence_error(db_session) -> None:
    """FK enforcement (see conftest's PRAGMA) means an unregistered node_id
    must fail loudly rather than silently orphaning metric rows."""
    repo = SqlAlchemyMetricsRepository(db_session)

    with pytest.raises(PersistenceError):
        repo.bulk_insert(
            node_id="never-registered",
            samples=[_sample()],
            collected_at=_now(),
            received_at=_now(),
        )


def test_find_previous_sample_returns_the_most_recent_within_window(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)
    now = _now()
    older = now - timedelta(seconds=200)
    newer = now - timedelta(seconds=60)
    repo.bulk_insert(
        node_id="node-1", samples=[_sample()], collected_at=older, received_at=now
    )
    repo.bulk_insert(
        node_id="node-1", samples=[_sample()], collected_at=newer, received_at=now
    )

    found = repo.find_previous_sample(
        node_id="node-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        before=now,
        window_seconds=300,
    )

    assert found is not None
    assert found.collected_at.tzinfo is not None
    # Sub-second precision differences across the SQLite round-trip are
    # irrelevant here; what matters is it picked "newer", not "older".
    assert abs((found.collected_at - newer).total_seconds()) < 1


def test_find_previous_sample_returns_none_outside_window(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)
    now = _now()
    too_old = now - timedelta(seconds=600)
    repo.bulk_insert(
        node_id="node-1", samples=[_sample()], collected_at=too_old, received_at=now
    )

    found = repo.find_previous_sample(
        node_id="node-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        before=now,
        window_seconds=300,
    )

    assert found is None


def test_find_previous_sample_returns_none_when_none_exist(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)

    found = repo.find_previous_sample(
        node_id="node-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        before=_now(),
        window_seconds=300,
    )

    assert found is None


def test_find_previous_sample_ignores_samples_at_or_after_before(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)
    now = _now()
    repo.bulk_insert(
        node_id="node-1", samples=[_sample()], collected_at=now, received_at=now
    )

    found = repo.find_previous_sample(
        node_id="node-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        before=now,
        window_seconds=300,
    )

    assert found is None


def test_find_previous_sample_ignores_other_metric_types(db_session) -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", _now())
    repo = SqlAlchemyMetricsRepository(db_session)
    now = _now()
    other_sample = MetricSample(
        metric_type=MetricType.MEMORY_USAGE_PERCENT, value=1.0, unit="percent"
    )
    repo.bulk_insert(
        node_id="node-1",
        samples=[other_sample],
        collected_at=now - timedelta(seconds=30),
        received_at=now,
    )

    found = repo.find_previous_sample(
        node_id="node-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        before=now,
        window_seconds=300,
    )

    assert found is None


def test_find_previous_sample_wraps_db_errors_as_persistence_error(
    db_session, monkeypatch
) -> None:
    repo = SqlAlchemyMetricsRepository(db_session)
    monkeypatch.setattr(
        db_session,
        "scalars",
        lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError("boom")),
    )

    with pytest.raises(PersistenceError):
        repo.find_previous_sample(
            node_id="node-1",
            metric_type=MetricType.CPU_USAGE_PERCENT,
            before=_now(),
            window_seconds=300,
        )
