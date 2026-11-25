"""OAuth 2.1 para o servidor MCP: clientes registados (registo dinâmico, ex.: claude.ai), autorizações dadas por
cada pessoa a cada cliente (grants) e os tokens (pedidos de autorização, códigos, acessos e renovações), estes
guardados só como hash.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("info", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "oauth_grants",
        sa.Column("grant_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("scopes", sa.String(120), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_used_at", sa.String(40), nullable=True),
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        # request (à espera do consentimento), code, access ou refresh.
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("grant_id", sa.String(64), nullable=True, index=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("scopes", sa.String(120), nullable=False, server_default=""),
        sa.Column("expires_at", sa.Float, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_grants")
    op.drop_table("oauth_clients")
