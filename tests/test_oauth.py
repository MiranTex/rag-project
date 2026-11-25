"""Login OAuth do servidor MCP: registo da aplicação, consentimento na interface, troca do código (PKCE),
renovação, recusa e revogação. O protocolo é o do SDK MCP; aqui testa-se o provider e o consentimento."""

import base64
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Route

from backend.api import oauth_consent
from backend.api.security import current_user
from backend.auth.oauth import OAuthProvider
from backend.auth.permissions import AuthenticatedUser
from backend.mcp_server import server as mcp
from backend.models import User
from backend.repositories.sql import SqlOAuthRepository, SqlUserRepository
from tests.repository_fixtures import sql_engine

API = "http://localhost"
APP = "http://app.local"
REDIRECT = "http://localhost:6274/callback"


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = sql_engine("sqlite", tmp_path)
    users = SqlUserRepository(engine)
    for name in ("ana", "rui"):
        users.add_or_replace(User(user_id=name, username=name, roles=["chat"], created_at="x"))
    repo = SqlOAuthRepository(engine)
    provider = OAuthProvider(lambda: repo, lambda: users, APP)
    monkeypatch.setattr(oauth_consent, "get_oauth_provider", lambda: provider)
    monkeypatch.setattr(oauth_consent, "get_oauth_repository", lambda: repo)
    monkeypatch.setattr(oauth_consent, "oauth_urls", lambda: (API, APP))
    monkeypatch.setattr(mcp, "get_users", lambda: users)

    routes, metadata_url = mcp.build_oauth_routes(provider, API)
    manager = mcp.StreamableHTTPSessionManager(app=mcp.build_server(mcp.build_tools()), stateless=True, json_response=True)

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(oauth_consent.router)
    app.router.routes.append(Route("/mcp", endpoint=mcp.McpEndpoint(manager, provider, metadata_url)))
    app.router.routes.extend(routes)
    who = {"user": "ana"}
    app.dependency_overrides[current_user] = lambda: AuthenticatedUser.of(users.find_by_id(who["user"]))
    with TestClient(app, base_url=API) as http:
        yield {"http": http, "who": who, "repo": repo, "users": users, "metadata_url": metadata_url}


def _register(http) -> str:
    response = http.post(
        "/register",
        json={"client_name": "Claude", "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none", "scope": "read write"},
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def _start(http, client_id: str, scope: str = "read write") -> tuple[str, str]:
    """Abre o /authorize como o browser e devolve (pedido, code_verifier)."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    response = http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "estado-1",
            "scope": scope,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    consent = urlparse(response.headers["location"])
    assert f"{consent.scheme}://{consent.netloc}{consent.path}" == f"{APP}/ligar/autorizar"
    return parse_qs(consent.query)["pedido"][0], verifier


def _redeem(http, client_id: str, redirect_to: str, verifier: str) -> dict:
    query = parse_qs(urlparse(redirect_to).query)
    assert query["state"] == ["estado-1"]
    response = http.post(
        "/token",
        data={"grant_type": "authorization_code", "code": query["code"][0], "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tools(http, access_token: str):
    return http.post(
        "/mcp",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )


def _connect(env, can_write: bool = True) -> tuple[str, dict]:
    http = env["http"]
    client_id = _register(http)
    pedido, verifier = _start(http, client_id)
    redirect_to = http.post(f"/oauth/requests/{pedido}/approve", json={"can_write": can_write}).json()["redirect_to"]
    return client_id, _redeem(http, client_id, redirect_to, verifier)


def test_mcp_401_points_clients_to_the_oauth_login(env):
    response = env["http"].post("/mcp", json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == f'Bearer resource_metadata="{env["metadata_url"]}"'
    resource = env["http"].get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == f"{API}/mcp" and resource["scopes_supported"] == ["read", "write"]
    server = env["http"].get("/.well-known/oauth-authorization-server").json()
    assert server["registration_endpoint"] == f"{API}/register" and server["code_challenge_methods_supported"] == ["S256"]


def test_consent_page_shows_who_asks_and_where_it_returns(env):
    http = env["http"]
    pedido, _ = _start(http, _register(http))
    info = http.get(f"/oauth/requests/{pedido}").json()
    assert (info["client_name"], info["redirect_host"], info["scopes"]) == ("Claude", "localhost:6274", ["read", "write"])
    assert http.get("/oauth/requests/inventado").status_code == 404


def test_full_flow_gives_a_token_that_works_on_mcp(env):
    _, tokens = _connect(env)
    assert tokens["access_token"].startswith("rag_oat_") and tokens["scope"] == "read write" and tokens["expires_in"] == 3600
    names = {t["name"] for t in _tools(env["http"], tokens["access_token"]).json()["result"]["tools"]}
    assert {"list_projects", "propose_item_changes"} <= names
    [grant] = env["repo"].list_grants("ana")
    assert grant.scopes == "read write" and grant.last_used_at is not None


def test_without_the_write_box_the_app_only_reads(env):
    _, tokens = _connect(env, can_write=False)
    assert tokens["scope"] == "read"
    names = {t["name"] for t in _tools(env["http"], tokens["access_token"]).json()["result"]["tools"]}
    assert "propose_item_changes" not in names


def test_codes_and_refresh_tokens_work_only_once(env):
    http = env["http"]
    client_id = _register(http)
    pedido, verifier = _start(http, client_id)
    redirect_to = http.post(f"/oauth/requests/{pedido}/approve", json={}).json()["redirect_to"]
    tokens = _redeem(http, client_id, redirect_to, verifier)
    code = parse_qs(urlparse(redirect_to).query)["code"][0]
    again = http.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier})
    assert again.status_code == 400
    # O pedido também já foi usado.
    assert http.post(f"/oauth/requests/{pedido}/approve", json={}).status_code == 404

    refresh = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id}
    renewed = http.post("/token", data=refresh)
    assert renewed.status_code == 200 and renewed.json()["refresh_token"] != tokens["refresh_token"]
    assert http.post("/token", data=refresh).status_code == 400
    assert _tools(http, renewed.json()["access_token"]).status_code == 200


def test_wrong_pkce_verifier_is_refused(env):
    http = env["http"]
    client_id = _register(http)
    pedido, _ = _start(http, client_id)
    redirect_to = http.post(f"/oauth/requests/{pedido}/approve", json={}).json()["redirect_to"]
    code = parse_qs(urlparse(redirect_to).query)["code"][0]
    response = http.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": "x" * 50})
    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_deny_returns_access_denied_to_the_app(env):
    http = env["http"]
    pedido, _ = _start(http, _register(http))
    query = parse_qs(urlparse(http.post(f"/oauth/requests/{pedido}/deny").json()["redirect_to"]).query)
    assert query["error"] == ["access_denied"] and query["state"] == ["estado-1"]
    assert env["repo"].list_grants("ana") == []


def test_revoking_in_the_account_cuts_access_and_refresh(env):
    http = env["http"]
    client_id, tokens = _connect(env)
    apps = http.get("/me/apps").json()
    assert apps["oauth_enabled"] and apps["mcp_url"] == f"{API}/mcp" and [a["name"] for a in apps["apps"]] == ["Claude"]

    env["who"]["user"] = "rui"
    assert http.get("/me/apps").json()["apps"] == []
    assert http.delete(f"/me/apps/{apps['apps'][0]['grant_id']}").status_code == 404  # não é dele
    env["who"]["user"] = "ana"

    assert http.delete(f"/me/apps/{apps['apps'][0]['grant_id']}").status_code == 200
    assert _tools(http, tokens["access_token"]).status_code == 401
    refresh = http.post("/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id})
    assert refresh.status_code == 400


def test_deactivated_users_lose_oauth_access(env):
    _, tokens = _connect(env)
    env["users"].add_or_replace(env["users"].find_by_id("ana").model_copy(update={"active": False}))
    assert _tools(env["http"], tokens["access_token"]).status_code == 401


def test_expired_requests_cannot_be_approved(env):
    http = env["http"]
    pedido, _ = _start(http, _register(http))
    record = env["repo"].get_token(hashlib.sha256(pedido.encode()).hexdigest(), "request")
    env["repo"].delete_token(record.token_hash)
    env["repo"].save_token(record.model_copy(update={"expires_at": time.time() - 1}))
    assert http.post(f"/oauth/requests/{pedido}/approve", json={}).status_code == 404
