"""Remediation actions table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLAYBOOK_ACTION_TYPE_VALUES = ("noop", "clear_directory", "restart_service")
_REMEDIATION_ACTION_STATUS_VALUES = (
    "blocked_by_safety_limit",
    "dispatched",
    "executed",
    "failed",
)


def upgrade() -> None:
    op.create_table(
        "remediation_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "node_id", sa.String(), sa.ForeignKey("nodes.node_id"), nullable=False
        ),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("rule_key", sa.String(), nullable=False),
        sa.Column("playbook_name", sa.String(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(*_PLAYBOOK_ACTION_TYPE_VALUES, name="playbookactiontype"),
            nullable=False,
        ),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*_REMEDIATION_ACTION_STATUS_VALUES, name="remediationactionstatus"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_remediation_actions_node_id_playbook_name_created_at",
        "remediation_actions",
        ["node_id", "playbook_name", "created_at"],
    )
    op.add_column(
        "alerts", sa.Column("remediated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("alerts", "remediated_at")
    op.drop_index(
        "ix_remediation_actions_node_id_playbook_name_created_at",
        table_name="remediation_actions",
    )
    op.drop_table("remediation_actions")
    sa.Enum(name="remediationactionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="playbookactiontype").drop(op.get_bind(), checkfirst=True)
