"""Tokens de acesso pessoais: ligam agentes externos (Claude Code, Codex…) ao servidor MCP em nome de uma pessoa.
Guarda-se só o hash SHA-256 do token; o token só é mostrado uma vez, ao criá-lo.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_tokens",
        sa.Column("token_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        # Início do token, para a pessoa o reconhecer na lista.
        sa.Column("prefix", sa.String(24), nullable=False),
        # O que o token pode fazer ("read" por agora; a escrita virá depois).
        sa.Column("scopes", sa.String(120), nullable=False, server_default="read"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_used_at", sa.String(40), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("access_tokens")
