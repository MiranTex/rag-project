"""Tokens de acesso pessoais para agentes externos (Claude Code, Codex…) que se ligam ao servidor MCP.

O token é aleatório (256 bits), por isso basta guardar o SHA-256 (não é uma palavra-passe que se possa adivinhar).
Só serve o servidor MCP, não o resto da API, e fica sem efeito quando a pessoa o revoga ou é desativada."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.auth.authenticators import AuthError
from backend.models import AccessToken, User
from backend.repositories.contracts import AccessTokenRepository, UserRepository

TOKEN_PREFIX = "rag_pat_"
# Não se grava "último uso" a cada chamada: um agente faz dezenas de pedidos seguidos.
TOUCH_EVERY = timedelta(minutes=5)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(tokens: AccessTokenRepository, user_id: str, name: str) -> tuple[str, AccessToken]:
    """Cria um token e devolve-o em claro (única vez) com o registo guardado."""
    plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
    record = AccessToken(
        token_id=str(uuid4()),
        user_id=user_id,
        name=name,
        token_hash=hash_token(plain),
        prefix=plain[: len(TOKEN_PREFIX) + 4],
        created_at=datetime.now(UTC).isoformat(),
    )
    tokens.add(record)
    return plain, record


def authenticate_token(tokens: AccessTokenRepository, users: UserRepository, plain: str) -> tuple[User, AccessToken]:
    if not plain.startswith(TOKEN_PREFIX):
        raise AuthError("Token inválido.")
    record = tokens.find_by_hash(hash_token(plain))
    user = users.find_by_id(record.user_id) if record else None
    if record is None or user is None or not user.active:
        raise AuthError("Token inválido, revogado ou de um utilizador desativado.")
    now = datetime.now(UTC)
    if record.last_used_at is None or now - datetime.fromisoformat(record.last_used_at) > TOUCH_EVERY:
        tokens.touch(record.token_id, now.isoformat())
    return user, record
