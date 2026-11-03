"""Configurações alteradas na aplicação (por cima das do .env).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
