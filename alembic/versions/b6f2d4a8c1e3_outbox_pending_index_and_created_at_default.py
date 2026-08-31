"""outbox pending partial index and payments created_at server default

Revision ID: b6f2d4a8c1e3
Revises: d4782bdc6c2d
Create Date: 2026-08-31 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6f2d4a8c1e3'
down_revision: str | Sequence[str] | None = 'd4782bdc6c2d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_outbox_pending_events",
        "outbox",
        ["id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.alter_column(
        "payments",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "payments",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_index("ix_outbox_pending_events", table_name="outbox")
