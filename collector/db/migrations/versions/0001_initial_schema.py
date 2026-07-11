"""Initial schema: nodes and metric_samples

Revision ID: 0001
Revises:
Create Date: 2026-07-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_METRIC_TYPE_VALUES = (
    "cpu.usage_percent",
    "memory.usage_percent",
    "memory.used_bytes",
    "memory.available_bytes",
    "disk.usage_percent",
    "disk.used_bytes",
    "disk.free_bytes",
    "network.bytes_sent",
    "network.bytes_recv",
)


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("node_id", sa.String(), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "metric_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "node_id", sa.String(), sa.ForeignKey("nodes.node_id"), nullable=False
        ),
        sa.Column(
            "metric_type",
            sa.Enum(*_METRIC_TYPE_VALUES, name="metrictype"),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_metric_samples_node_id_collected_at",
        "metric_samples",
        ["node_id", "collected_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_samples_node_id_collected_at", table_name="metric_samples")
    op.drop_table("metric_samples")
    op.drop_table("nodes")
    sa.Enum(name="metrictype").drop(op.get_bind(), checkfirst=True)
