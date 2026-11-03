"""Área de pesquisa: projetos, membros, documentos fixados, caderno, comentários, matriz de literatura,
pesquisas guardadas e avaliações das respostas.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("question", sa.Text, nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("work_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "project_members",
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
    )
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])

    op.create_table(
        "project_documents",
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), primary_key=True),
        sa.Column("added_by", sa.String(64), nullable=False),
        sa.Column("added_at", sa.String(40), nullable=False),
    )

    op.create_table(
        "notebook_items",
        sa.Column("item_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default=""),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("source", sa.JSON, nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_notebook_items_project_id", "notebook_items", ["project_id"])

    op.create_table(
        "project_comments",
        sa.Column("comment_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_project_comments_project_id", "project_comments", ["project_id"])

    op.create_table(
        "project_matrices",
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )

    op.create_table(
        "saved_searches",
        sa.Column("search_id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("filters", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_seen_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_saved_searches_owner_id", "saved_searches", ["owner_id"])

    op.create_table(
        "answer_feedback",
        sa.Column("feedback_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("sources", sa.JSON, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "answer_feedback",
        "saved_searches",
        "project_matrices",
        "project_comments",
        "notebook_items",
        "project_documents",
        "project_members",
        "projects",
    ):
        op.drop_table(table)
