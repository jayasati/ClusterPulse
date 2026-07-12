"""Index metric_samples.received_at for retention pruning

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The retention job (docs/adr/010-retention-policy.md) deletes
    # metric_samples by received_at cutoff; without this index every batch
    # would sequential-scan what is by far the largest table.
    op.create_index(
        "ix_metric_samples_received_at",
        "metric_samples",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_samples_received_at", table_name="metric_samples")
