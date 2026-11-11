"""Fornecedores de LLM configurados na aplicação (chave, URL, modelos) e qual está ativo.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("api_key", sa.Text, nullable=False, server_default=""),
        sa.Column("base_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("chat_model", sa.String(255), nullable=False, server_default=""),
        sa.Column("utility_model", sa.String(255), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_providers")
