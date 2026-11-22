"""Vetores no PostgreSQL (pgvector): extensão vector e tabela vector_embeddings. Só em PostgreSQL e só se a
extensão estiver disponível no servidor; nos outros casos não faz nada (SQLite dos testes, ou extensão
instalada mais tarde: o VectorStore cria a tabela ao arrancar).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Igual a backend/services/vector_store.py (SCHEMA_STATEMENTS), copiado para a migração não mudar com o código.
STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """CREATE TABLE IF NOT EXISTS vector_embeddings (
        collection VARCHAR(128) NOT NULL,
        id TEXT NOT NULL,
        document_id TEXT,
        embedding vector NOT NULL,
        document TEXT NOT NULL DEFAULT '',
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY (collection, id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_vector_embeddings_document ON vector_embeddings (collection, document_id)",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    available = bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).scalar()
    if not available:
        return
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS vector_embeddings")
