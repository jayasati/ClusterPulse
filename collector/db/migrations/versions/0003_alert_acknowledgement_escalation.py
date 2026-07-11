"""Alert acknowledgement and escalation columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("alerts", sa.Column("acknowledged_by", sa.String(), nullable=True))
    op.add_column(
        "alerts", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("alerts", "escalated_at")
    op.drop_column("alerts", "acknowledged_by")
    op.drop_column("alerts", "acknowledged_at")
