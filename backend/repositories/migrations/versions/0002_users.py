"""Utilizadores e autoria dos documentos (quem carregou, quem aprovou e o texto aprovado).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("roles", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_external_id", "users", ["external_id"], unique=True)

    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("uploaded_by", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("approved_by", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("approved_fingerprint", sa.String(64), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("approved_fingerprint")
        batch.drop_column("approved_by")
        batch.drop_column("uploaded_by")
    op.drop_table("users")
