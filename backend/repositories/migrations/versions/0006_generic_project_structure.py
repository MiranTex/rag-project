"""Estrutura genérica dos projetos: secções e estados definidos por cada projeto; nas entradas do caderno, a
secção, uma referência curta, o estado e campos livres.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("structure", sa.JSON, nullable=False, server_default=sa.text("'{}'")))
    with op.batch_alter_table("notebook_items") as batch:
        batch.add_column(sa.Column("section", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("ref", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("status", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("fields", sa.JSON, nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table("notebook_items") as batch:
        for column in ("fields", "status", "ref", "section"):
            batch.drop_column(column)
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("structure")
