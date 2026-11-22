"""Conversas do chat guardadas nos projetos e convites por email.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_conversations",
        sa.Column("conversation_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("messages", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_project_conversations_project_id", "project_conversations", ["project_id"])

    op.create_table(
        "project_invitations",
        sa.Column("invitation_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("accepted_by", sa.String(64), nullable=True),
        sa.Column("accepted_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_project_invitations_project_id", "project_invitations", ["project_id"])


def downgrade() -> None:
    op.drop_table("project_invitations")
    op.drop_table("project_conversations")
