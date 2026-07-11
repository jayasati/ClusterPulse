"""SQLAlchemy-backed ``MetricsRepository`` implementation."""

from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from collector.db.models.metric_sample import MetricSampleModel
from shared.contracts.v1.metrics import MetricSample
from shared.exceptions import PersistenceError


class SqlAlchemyMetricsRepository:
    """Persists metric samples via SQLAlchemy."""

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
