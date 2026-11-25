"""O lado da interface do login OAuth do servidor MCP: a página de consentimento (/ligar/autorizar) e a lista de
aplicações ligadas na conta. O protocolo em si está em auth/oauth.py e no SDK MCP."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.security import require
from backend.auth.access_tokens import WRITE
from backend.auth.authenticators import AuthError
from backend.auth.oauth import client_label
from backend.auth.permissions import CHAT_USE, AuthenticatedUser
from backend.dependencies import get_oauth_provider, get_oauth_repository, oauth_urls

router = APIRouter(tags=["oauth"])

# O MCP dá o mesmo acesso que o agente do chat.
can_connect = require(CHAT_USE)


class Approval(BaseModel):
    # Também propor alterações ao caderno e comentar (só se a aplicação o pediu).
    can_write: bool = False


def _provider():
    provider = get_oauth_provider()
    if provider is None:
        raise HTTPException(status_code=404, detail="O login de aplicações não está ativo neste servidor.")
    return provider


def _pending(request_id: str):
    pending = _provider().pending_request(request_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Este pedido de autorização expirou ou já foi usado. Volta a ligar a aplicação.")
    return pending


@router.get("/oauth/requests/{request_id}")
def get_request(request_id: str, user: AuthenticatedUser = Depends(can_connect)) -> dict:
    record, client = _pending(request_id)
    return {
        "client_name": client_label(client),
        "client_uri": client.get("client_uri") or "",
        # Para onde a pessoa volta: ajuda a reconhecer uma aplicação falsa com um nome conhecido.
        "redirect_host": urlparse(record.data["redirect_uri"]).netloc,
        "scopes": record.scopes.split(),
        "user": user.user.display_name or user.user.username,
    }


@router.post("/oauth/requests/{request_id}/approve")
def approve(request_id: str, payload: Approval, user: AuthenticatedUser = Depends(can_connect)) -> dict:
    _pending(request_id)
    scopes = ["read", WRITE] if payload.can_write else ["read"]
    try:
        return {"redirect_to": _provider().approve(request_id, user.user, scopes)}
    except AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/oauth/requests/{request_id}/deny")
def deny(request_id: str, user: AuthenticatedUser = Depends(can_connect)) -> dict:
    _pending(request_id)
    return {"redirect_to": _provider().deny(request_id)}


@router.get("/me/apps")
def list_apps(user: AuthenticatedUser = Depends(can_connect)) -> dict:
    api_url, _ = oauth_urls()
    enabled = get_oauth_provider() is not None
    repo = get_oauth_repository()
    apps = [
        {
            "grant_id": g.grant_id,
            "name": client_label(repo.get_client(g.client_id)),
            "scopes": g.scopes.split(),
            "created_at": g.created_at,
            "last_used_at": g.last_used_at,
        }
        for g in (repo.list_grants(user.user_id) if enabled else [])
    ]
    return {"oauth_enabled": enabled, "mcp_url": f"{api_url}/mcp" if api_url else "", "apps": apps}


@router.delete("/me/apps/{grant_id}")
def revoke_app(grant_id: str, user: AuthenticatedUser = Depends(can_connect)) -> dict:
    if not get_oauth_repository().delete_grant(user.user_id, grant_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.")
    return {"message": "Acesso revogado."}
