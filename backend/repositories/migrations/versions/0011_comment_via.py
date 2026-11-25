"""Origem dos comentários escritos por um agente externo (MCP): o nome do token, ex.: "Claude Code do portátil".
Vazio num comentário escrito na interface.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_comments", sa.Column("via", sa.String(120), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("project_comments", "via")
