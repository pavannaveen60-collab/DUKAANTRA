"""Add the nullable shop phone field.

Revision ID: 202611110002
Revises: 202611110001
"""

from alembic import op
import sqlalchemy as sa


revision = "202611110002"
down_revision = "202611110001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shops",
        sa.Column("phone", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading would delete merchant shop phone values; restore from a "
        "verified backup and perform a reviewed data-preserving rollback."
    )
