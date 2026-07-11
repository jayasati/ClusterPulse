"""The metric samples table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from collector.db.base import Base
from collector.db.enum_column import str_enum_column
from shared.constants import MetricType


class MetricSampleModel(Base):
    """One persisted ``shared.contracts.v1.metrics.MetricSample`` observation.

    Kept as its own table (rather than embedding samples as JSON on a
    payload row) so it can be indexed and queried per node/metric — the
    access pattern the future Rule Engine (Phase 3) will need.
    """

    __tablename__ = "metric_samples"
    __table_args__ = (
        Index("ix_metric_samples_node_id_collected_at", "node_id", "collected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    metric_type: Mapped[MetricType] = mapped_column(str_enum_column(MetricType))
    value: Mapped[float]
    unit: Mapped[str]
    labels: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
