"""Add 'staleness' to the rulekind enum

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the transaction Alembic
    # wraps migrations in (PostgreSQL restriction), hence the autocommit
    # block. IF NOT EXISTS makes re-runs harmless.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rulekind ADD VALUE IF NOT EXISTS 'staleness'")


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum type; a true downgrade
    # would require rebuilding the type and every column using it. The
    # extra value is harmless when unused, so downgrade is a no-op —
    # consistent with the value being additive-only.
    pass
