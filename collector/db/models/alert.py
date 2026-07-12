"""The alerts table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from collector.db.base import Base
from collector.db.enum_column import str_enum_column
from collector.enums import AlertStatus, RuleKind
from shared.constants import Severity


class AlertModel(Base):
    """One alert produced by the Rule Engine.

    Only one row may be ``firing`` at a time per ``(node_id, rule_key)`` —
    enforced at the application level (``AlertEvaluationService``), not by
    a database constraint. See ``docs/adr/006-alert-lifecycle.md``.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    rule_key: Mapped[str]
    rule_kind: Mapped[RuleKind] = mapped_column(str_enum_column(RuleKind))
    severity: Mapped[Severity] = mapped_column(str_enum_column(Severity))
    status: Mapped[AlertStatus] = mapped_column(str_enum_column(AlertStatus))
    description: Mapped[str]
    triggering_value: Mapped[float]
    bound: Mapped[float]
    first_fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    acknowledged_by: Mapped[str | None] = mapped_column(default=None)
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    remediated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
