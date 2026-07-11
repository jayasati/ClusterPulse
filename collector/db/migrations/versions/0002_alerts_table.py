"""Alerts table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RULE_KIND_VALUES = ("threshold", "rate_of_change")
_SEVERITY_VALUES = ("warning", "critical")
_ALERT_STATUS_VALUES = ("firing", "resolved")


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "node_id", sa.String(), sa.ForeignKey("nodes.node_id"), nullable=False
        ),
        sa.Column("rule_key", sa.String(), nullable=False),
        sa.Column(
            "rule_kind", sa.Enum(*_RULE_KIND_VALUES, name="rulekind"), nullable=False
        ),
        sa.Column(
            "severity", sa.Enum(*_SEVERITY_VALUES, name="severity"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(*_ALERT_STATUS_VALUES, name="alertstatus"),
            nullable=False,
        ),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("triggering_value", sa.Float(), nullable=False),
        sa.Column("bound", sa.Float(), nullable=False),
        sa.Column("first_fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_alerts_node_id_rule_key_status",
        "alerts",
        ["node_id", "rule_key", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_node_id_rule_key_status", table_name="alerts")
    op.drop_table("alerts")
    sa.Enum(name="alertstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="rulekind").drop(op.get_bind(), checkfirst=True)
