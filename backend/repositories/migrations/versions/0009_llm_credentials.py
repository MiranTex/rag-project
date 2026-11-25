"""Chaves de API próprias: de um utilizador (para não gastar a da plataforma) ou de um projeto (o projeto paga).
A chave fica cifrada (ver services/secret_box.py).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_credentials",
        # "user" ou "project"; owner_id é o user_id ou o project_id.
        sa.Column("scope", sa.String(16), primary_key=True),
        sa.Column("owner_id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=False, server_default=""),
        sa.Column("chat_model", sa.String(255), nullable=False, server_default=""),
        sa.Column("utility_model", sa.String(255), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_credentials")
