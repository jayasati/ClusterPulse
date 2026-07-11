"""SQLAlchemy-backed ``MetricsRepository`` implementation."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from collector.db.models.metric_sample import MetricSampleModel
from collector.db.timeutil import ensure_utc
from collector.repositories.protocols import MetricSampleRecord
from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample
from shared.exceptions import PersistenceError


class SqlAlchemyMetricsRepository:
    """Persists and queries metric samples via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def bulk_insert(
        self,
        node_id: str,
        samples: list[MetricSample],
        collected_at: datetime,
        received_at: datetime,
    ) -> None:
        """Persist every sample in ``samples`` for ``node_id`` in one transaction."""
        rows = [
            MetricSampleModel(
                node_id=node_id,
                metric_type=sample.metric_type,
                value=sample.value,
                unit=sample.unit,
                labels=sample.labels,
                collected_at=collected_at,
                received_at=received_at,
            )
            for sample in samples
        ]
        try:
            self._session.add_all(rows)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                "failed to persist metric samples", context={"node_id": node_id}
            ) from exc

    def find_previous_sample(
        self,
        node_id: str,
        metric_type: MetricType,
        before: datetime,
        window_seconds: float,
    ) -> MetricSampleRecord | None:
        """Return the most recent sample in ``[before - window_seconds, before)``."""
        since = before - timedelta(seconds=window_seconds)
        statement = (
            select(MetricSampleModel)
            .where(
                MetricSampleModel.node_id == node_id,
                MetricSampleModel.metric_type == metric_type,
                MetricSampleModel.collected_at < before,
                MetricSampleModel.collected_at >= since,
            )
            .order_by(MetricSampleModel.collected_at.desc())
            .limit(1)
        )
        try:
            row = self._session.scalars(statement).first()
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to query previous metric sample",
                context={"node_id": node_id, "metric_type": metric_type.value},
            ) from exc
        return _to_record(row) if row is not None else None


def _to_record(row: MetricSampleModel) -> MetricSampleRecord:
    return MetricSampleRecord(
        node_id=row.node_id,
        metric_type=row.metric_type,
        value=row.value,
        unit=row.unit,
        labels=row.labels,
        collected_at=ensure_utc(row.collected_at),
        received_at=ensure_utc(row.received_at),
    )
