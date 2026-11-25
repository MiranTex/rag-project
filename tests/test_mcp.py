"""Servidor MCP para agentes externos: tokens pessoais, a API que os gere e o endpoint /mcp (JSON-RPC)."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.routing import Route

import backend.research.access as access
from backend.agent.tools.base import ToolContext, ToolResult, tool
from backend.api import access_tokens as tokens_api
from backend.api.security import current_user
from backend.auth.access_tokens import authenticate_token, hash_token, issue_token
from backend.auth.authenticators import AuthError
from backend.auth.permissions import AuthenticatedUser
from backend.mcp_server import server as mcp
from backend.models import User
from backend.repositories.research_sql import SqlResearchRepository
from backend.repositories.sql import SqlAccessTokenRepository, SqlUserRepository
from backend.research.models import Project, ProjectMember
from tests.repository_fixtures import sql_engine


@pytest.fixture
def db(tmp_path):
    engine = sql_engine("sqlite", tmp_path)
    users = SqlUserRepository(engine)
    for name, roles in (("ana", ["chat"]), ("rui", ["chat"]), ("leitor", ["manager"])):
        users.add_or_replace(User(user_id=name, username=name, roles=roles, created_at="x"))
    return {"engine": engine, "users": users, "tokens": SqlAccessTokenRepository(engine), "research": SqlResearchRepository(engine)}


# ---------------------------------------------------------------- tokens


def test_tokens_are_stored_as_hash_and_authenticate_their_owner(db):
    plain, record = issue_token(db["tokens"], "ana", "Claude Code")
    assert plain.startswith("rag_pat_") and record.token_hash == hash_token(plain)
    assert plain not in json.dumps([t.model_dump() for t in db["tokens"].list_for("ana")])

    user, used = authenticate_token(db["tokens"], db["users"], plain)
    assert user.user_id == "ana" and used.token_id == record.token_id
    assert db["tokens"].list_for("ana")[0].last_used_at is not None

    for bad in ("rag_pat_inventado", "outro-formato", plain + "x"):
        with pytest.raises(AuthError):
            authenticate_token(db["tokens"], db["users"], bad)


def test_revoked_tokens_and_deactivated_users_stop_working(db):
    plain, record = issue_token(db["tokens"], "ana", "portátil")
    assert db["tokens"].delete("rui", record.token_id) is False  # só o dono revoga
    db["users"].add_or_replace(db["users"].find_by_id("ana").model_copy(update={"active": False}))
    with pytest.raises(AuthError):
        authenticate_token(db["tokens"], db["users"], plain)
    assert db["tokens"].delete("ana", record.token_id) is True
    assert db["tokens"].find_by_hash(hash_token(plain)) is None


def test_last_used_is_not_written_on_every_call(db, monkeypatch):
    plain, record = issue_token(db["tokens"], "ana", "x")
    recent = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    db["tokens"].touch(record.token_id, recent)
    authenticate_token(db["tokens"], db["users"], plain)
    assert db["tokens"].list_for("ana")[0].last_used_at == recent


def test_token_api_shows_the_token_only_once(db, monkeypatch):
    monkeypatch.setattr(tokens_api, "get_access_tokens", lambda: db["tokens"])
    app = FastAPI()
    app.include_router(tokens_api.router)
    who = {"user": "ana"}
    app.dependency_overrides[current_user] = lambda: AuthenticatedUser.of(db["users"].find_by_id(who["user"]))
    http = TestClient(app)

    created = http.post("/me/tokens", json={"name": "Codex"}).json()
    assert created["token"].startswith("rag_pat_") and created["scopes"] == ["read"]
    listed = http.get("/me/tokens").json()
    assert [t["name"] for t in listed] == ["Codex"] and "token" not in listed[0]
    assert http.post("/me/tokens", json={"name": ""}).status_code == 422

    who["user"] = "rui"
    assert http.get("/me/tokens").json() == []
    assert http.delete(f"/me/tokens/{created['token_id']}").status_code == 404
    who["user"] = "ana"
    assert http.delete(f"/me/tokens/{created['token_id']}").status_code == 200


# ---------------------------------------------------------------- endpoint /mcp


class EchoParams(BaseModel):
    query: str


@tool(name="echo_documents", description="Tool de teste.", params=EchoParams)
def echo_documents(params: EchoParams, context) -> ToolResult:
    return ToolResult(content={"query": params.query, "scope": context.scope_document_ids}, summary="ok")


@pytest.fixture
def client(db, monkeypatch):
    research = db["research"]
    research.save_project(Project(project_id="p1", owner_id="ana", title="Tese", question="Energia", created_at="x", updated_at="x"))
    research.set_member(ProjectMember(project_id="p1", user_id="rui", role="viewer"))

    class Registry:
        def find_by_id(self, _):
            return None

    for module in (access, mcp):
        monkeypatch.setattr(module, "get_research_repository", lambda: research)
    monkeypatch.setattr(access, "get_registry", lambda: Registry())
    monkeypatch.setattr(mcp, "get_registry", lambda: Registry())
    monkeypatch.setattr(mcp, "get_access_tokens", lambda: db["tokens"])
    monkeypatch.setattr(mcp, "get_users", lambda: db["users"])
    # O contexto real abre o pipeline (pgvector); aqui chega o âmbito e o caderno do projeto.
    monkeypatch.setattr(
        mcp,
        "research_context",
        lambda user, scope=None: ToolContext(pipeline=None, vector_store=None, registry=None, export_store=None, scope_document_ids=scope),
    )
    monkeypatch.setattr(mcp, "get_users", lambda: db["users"])
    tools = {**mcp.build_tools(), "echo_documents": mcp._wrap(echo_documents, needs_project=False)}
    manager = mcp.StreamableHTTPSessionManager(app=mcp.build_server(tools), stateless=True, json_response=True)

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.router.routes.append(Route("/mcp", endpoint=mcp.McpEndpoint(manager)))
    with TestClient(app) as http:
        tokens = {name: issue_token(db["tokens"], name, "teste")[0] for name in ("ana", "rui", "leitor")}
        tokens |= {f"{name}+w": issue_token(db["tokens"], name, f"Claude Code de {name}", can_write=True)[0] for name in ("ana", "rui")}

        def rpc(method: str, params: dict | None = None, token: str | None = "ana"):
            headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
            if token:
                headers["Authorization"] = f"Bearer {tokens.get(token, token)}"
            return http.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})

        yield rpc


def _tool_result(response) -> tuple[bool, object]:
    result = response.json()["result"]
    text = result["content"][0]["text"]
    try:
        return result["isError"], json.loads(text)
    except json.JSONDecodeError:
        return result["isError"], text


def test_mcp_requires_a_personal_token(client):
    assert client("tools/list", token=None).status_code == 401
    assert client("tools/list", token="rag_pat_falso").status_code == 401
    assert client("tools/list", token="eyJ.sessao.web").status_code == 401


def test_mcp_lists_tools_with_optional_project(client):
    response = client("tools/list")
    assert response.status_code == 200
    tools = {t["name"]: t for t in response.json()["result"]["tools"]}
    assert {"list_projects", "get_project", "search_documents", "list_project_items", "echo_documents"} <= set(tools)
    # Um token só de leitura não vê as tools de escrita.
    assert not set(tools) & {"propose_item_changes", "add_comment"}
    schema = tools["echo_documents"]["inputSchema"]
    assert "project_id" in schema["properties"] and schema["required"] == ["query"]


def test_mcp_tools_respect_project_membership(client):
    error, data = _tool_result(client("tools/call", {"name": "list_projects", "arguments": {}}))
    assert not error and [(p["title"], p["my_role"]) for p in data["projects"]] == [("Tese", "owner")]

    error, data = _tool_result(client("tools/call", {"name": "list_projects", "arguments": {}}, token="rui"))
    assert data["projects"][0]["my_role"] == "viewer"

    error, data = _tool_result(client("tools/call", {"name": "get_project", "arguments": {"project_id": "p1"}}))
    assert not error and data["title"] == "Tese" and "Objetivo do projeto: Energia" in data["description"]

    error, data = _tool_result(client("tools/call", {"name": "get_project", "arguments": {"project_id": "p1"}}, token="leitor"))
    assert error and data == "Projeto não encontrado."


def test_mcp_wraps_the_agent_tools_with_the_project_scope(client):
    error, data = _tool_result(client("tools/call", {"name": "echo_documents", "arguments": {"query": "energia"}}))
    assert not error and data["result"] == {"query": "energia", "scope": None}

    error, data = _tool_result(client("tools/call", {"name": "echo_documents", "arguments": {"query": "x", "project_id": "p1"}}))
    assert not error and data["result"]["scope"] == []

    error, data = _tool_result(client("tools/call", {"name": "echo_documents", "arguments": {"query": "x", "project_id": "p1"}}, token="leitor"))
    assert error and data == "Projeto não encontrado."

    error, data = _tool_result(client("tools/call", {"name": "echo_documents", "arguments": {}}))
    assert error and "query" in data


def test_real_tool_list_writes_only_through_proposals_and_comments():
    tools = mcp.build_tools()
    assert {"search_documents", "read_document", "list_project_items", "list_projects"} <= set(tools)
    assert {name for name, t in tools.items() if t.write} == {"propose_item_changes", "add_comment"}
    assert not set(tools) & {"export_csv", "export_document", "calculate"}


PROPOSAL = {
    "project_id": "p1",
    "request": "Acrescenta a conclusão sobre LED",
    "summary": "Proponho uma entrada nova com o resultado principal [relatorio.pdf, p.2].",
    "changes": [{"action": "create", "title": "LED reduz 31%", "text": "Redução de 31% [relatorio.pdf, p.2]", "basis": "documents", "reason": "Resultado central"}],
}


def test_write_tools_need_a_write_token(client):
    write_tools = {t["name"] for t in client("tools/list", token="ana+w").json()["result"]["tools"]}
    assert {"propose_item_changes", "add_comment"} <= write_tools
    error, data = _tool_result(client("tools/call", {"name": "propose_item_changes", "arguments": PROPOSAL}))
    assert error and "não permitida" in data


def test_proposals_wait_in_a_project_conversation_signed_by_the_token(client, db):
    error, data = _tool_result(client("tools/call", {"name": "propose_item_changes", "arguments": PROPOSAL}, token="ana+w"))
    assert not error and data["proposed"] == 1
    conversation = db["research"].get_conversation(data["conversation_id"])
    assert conversation.created_by == "ana" and conversation.title.startswith("Claude Code de ana:")
    [message] = conversation.messages
    assert message["mode"] == "agent" and message["via"] == "Claude Code de ana" and message["projectId"] == "p1"
    [proposal] = message["proposals"]
    assert proposal["via"] == "Claude Code de ana" and proposal["changes"]["title"] == "LED reduz 31%" and "decision" not in proposal
    assert db["research"].list_items("p1") == []  # nada entra no caderno sem alguém aceitar

    again = {**PROPOSAL, "conversation_id": data["conversation_id"], "request": "E os sensores?"}
    error, data2 = _tool_result(client("tools/call", {"name": "propose_item_changes", "arguments": again}, token="ana+w"))
    assert not error and data2["conversation_id"] == data["conversation_id"]
    assert len(db["research"].get_conversation(data["conversation_id"]).messages) == 2

    # A conversa de outra pessoa não serve para acrescentar.
    error, data3 = _tool_result(client("tools/call", {"name": "propose_item_changes", "arguments": again}, token="rui+w"))
    assert error and "conversation_id" in data3


def test_proposals_are_checked_like_the_chat_agent(client):
    bad = {**PROPOSAL, "changes": [{"action": "create", "title": "x", "text": "sem citação", "basis": "documents"}]}
    error, data = _tool_result(client("tools/call", {"name": "propose_item_changes", "arguments": bad}, token="ana+w"))
    assert error and "citações" in data
    other = {**PROPOSAL, "project_id": "nao-existe"}
    error, data = _tool_result(client("tools/call", {"name": "propose_item_changes", "arguments": other}, token="ana+w"))
    assert error and data == "Projeto não encontrado."


def test_comments_are_signed_with_the_token(client, db):
    error, data = _tool_result(client("tools/call", {"name": "add_comment", "arguments": {"project_id": "p1", "text": "Revi as fontes."}}, token="rui+w"))
    assert not error
    [comment] = db["research"].list_comments("p1")
    assert (comment.author_id, comment.via, comment.item_id) == ("rui", "Claude Code de rui", None)
    error, data = _tool_result(client("tools/call", {"name": "add_comment", "arguments": {"project_id": "p1", "text": "x", "item": "RF-9"}}, token="rui+w"))
    assert error and "Entrada não encontrada" in data
