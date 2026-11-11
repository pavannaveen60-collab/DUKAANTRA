"""Add persistent idempotency records for manual order creation.

Revision ID: 202611110003
Revises: 202611110002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202611110003"
down_revision = "202611110002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "shop_id",
            "operation",
            "key_hash",
            name="uq_order_idempotency_scope_key",
        ),
    )
    op.create_index(
        "ix_order_idempotency_order_id",
        "order_idempotency",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_idempotency_order_id",
        table_name="order_idempotency",
    )
    op.drop_table("order_idempotency")
