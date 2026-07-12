"""The remediation actions table — the Playbook audit log."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from collector.db.base import Base
from collector.db.enum_column import str_enum_column
from collector.enums import RemediationActionStatus
from shared.contracts.v1.remediation import PlaybookActionType


class RemediationActionModel(Base):
    """One remediation decision made by the ``RemediationEngine``.

    Every decision is recorded, whether dispatched or blocked by a Safety
    Limit — this table is the durable, queryable audit trail ROADMAP Phase
    5 requires, distinct from ``structlog`` output. See
    ``docs/adr/007-remediation-safety.md``.
    """

    __tablename__ = "remediation_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    rule_key: Mapped[str]
    playbook_name: Mapped[str]
    action_type: Mapped[PlaybookActionType] = mapped_column(
        str_enum_column(PlaybookActionType)
    )
    parameters: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    status: Mapped[RemediationActionStatus] = mapped_column(
        str_enum_column(RemediationActionStatus)
    )
    reason: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
