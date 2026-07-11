"""The node registry table."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from collector.db.base import Base


class NodeModel(Base):
    """A node the Collector has heard from at least once.

    Rows are created lazily on first successful authenticated push — there
    is no separate node-provisioning step in Phase 2 (see
    ``docs/adr/003-heartbeat-deadman-switch.md``).
    """

    __tablename__ = "nodes"

    node_id: Mapped[str] = mapped_column(primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
