"""A minha conta → Ligar agentes: tokens pessoais para o servidor MCP (Claude Code, Codex…).

O token só aparece na resposta de criação; depois só se vê o nome, o início e quando foi usado."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.security import require
from backend.auth.access_tokens import issue_token
from backend.auth.permissions import CHAT_USE, AuthenticatedUser
from backend.dependencies import get_access_tokens
from backend.models import AccessToken

router = APIRouter(prefix="/me/tokens", tags=["access-tokens"])

# O servidor MCP dá o mesmo acesso que o agente do chat.
can_connect = require(CHAT_USE)
MAX_TOKENS = 20


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _view(token: AccessToken) -> dict:
    return {
        "token_id": token.token_id,
        "name": token.name,
        "prefix": token.prefix,
        "scopes": token.scopes.split(),
        "created_at": token.created_at,
        "last_used_at": token.last_used_at,
    }


@router.get("")
def list_tokens(user: AuthenticatedUser = Depends(can_connect)) -> list[dict]:
    return [_view(t) for t in get_access_tokens().list_for(user.user_id)]


@router.post("")
def create_token(payload: TokenCreate, user: AuthenticatedUser = Depends(can_connect)) -> dict:
    tokens = get_access_tokens()
    if len(tokens.list_for(user.user_id)) >= MAX_TOKENS:
        raise HTTPException(status_code=400, detail=f"Máximo de {MAX_TOKENS} tokens: revoga algum que já não uses.")
    plain, record = issue_token(tokens, user.user_id, payload.name.strip())
    return {**_view(record), "token": plain}


@router.delete("/{token_id}")
def revoke_token(token_id: str, user: AuthenticatedUser = Depends(can_connect)) -> dict:
    if not get_access_tokens().delete(user.user_id, token_id):
        raise HTTPException(status_code=404, detail="Token não encontrado.")
    return {"message": "Token revogado."}
