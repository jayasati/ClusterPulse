"""Unit tests for SqlAlchemyMetricsRepository."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

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
