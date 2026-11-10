"""Esquema inicial: documentos, extração por página, ficha e fila de trabalhos.

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("document_id", sa.String(64), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False, server_default=""),
        sa.Column("storage_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("name_source", sa.String(16), nullable=False, server_default="original"),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alert_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("title", sa.Text, nullable=False, server_default=""),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("document_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    op.create_table(
        "extraction_pages",
        sa.Column("document_id", sa.String(64), primary_key=True),
        sa.Column("page", sa.Integer, primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("alerts", sa.JSON, nullable=False),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("edited", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "document_metadata",
        sa.Column("document_id", sa.String(64), primary_key=True),
        sa.Column("data", sa.JSON, nullable=False),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=True),
        sa.Column("finished_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_jobs_document_id", "jobs", ["document_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("document_metadata")
    op.drop_table("extraction_pages")
    op.drop_table("documents")
