"""Chaves de API próprias (pessoa e projeto): cifra, repositório, quem paga cada pedido e a API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import backend.dependencies as dependencies
import backend.research.access as access
from backend.api import llm_keys as api
from backend.api.security import current_user
from backend.auth.permissions import AuthenticatedUser
from backend.models import LLMProviderConfig, User
from backend.repositories.research_sql import SqlResearchRepository
from backend.repositories.sql import SqlLLMCredentialsRepository, llm_credentials
from backend.research.models import Project, ProjectMember
from backend.services.llm_providers import choose_llm
from backend.services.secret_box import SecretBox, SecretBoxUnavailable
from tests.repository_fixtures import SQL_BACKENDS, sql_engine

PLATFORM = LLMProviderConfig(provider="openrouter", api_key="sk-platform", active=True)


# ---------------------------------------------------------------- cifra e repositório


def test_secret_box_round_trip_and_wrong_master_key():
    box = SecretBox("mestra-1")
    token = box.encrypt("sk-ant-segredo")
    assert token != "sk-ant-segredo" and box.decrypt(token) == "sk-ant-segredo"
    # Com outra chave mestra a chave não se lê (fica como se não existisse), em vez de rebentar.
    assert SecretBox("mestra-2").decrypt(token) == ""
    assert box.encrypt("") == "" and box.decrypt("") == ""


def test_secret_box_without_master_key_refuses_to_store():
    box = SecretBox("")
    assert not box.available
    with pytest.raises(SecretBoxUnavailable):
        box.encrypt("sk-x")


@pytest.fixture(params=SQL_BACKENDS)
def engine(request, tmp_path):
    return sql_engine(request.param, tmp_path)


def test_credentials_are_stored_encrypted_and_scoped(engine):
    repo = SqlLLMCredentialsRepository(engine, SecretBox("mestra"))
    assert repo.get("user", "ana") is None

    repo.save("user", "ana", LLMProviderConfig(provider="anthropic", api_key="sk-ant-da-ana"), "ana")
    repo.save("project", "ana", LLMProviderConfig(provider="openai", api_key="sk-proj", chat_model="gpt-x"), "ana")

    with engine.connect() as conn:
        stored = [row.api_key_encrypted for row in conn.execute(select(llm_credentials))]
    assert stored and all("sk-" not in value for value in stored)

    assert repo.get("user", "ana").api_key == "sk-ant-da-ana"
    assert (repo.get("project", "ana").provider, repo.get("project", "ana").chat_model) == ("openai", "gpt-x")

    repo.save("user", "ana", LLMProviderConfig(provider="openrouter", api_key="sk-or-novo"), "ana")
    assert (repo.get("user", "ana").provider, repo.get("user", "ana").api_key) == ("openrouter", "sk-or-novo")

    assert repo.delete("user", "ana") is True
    assert repo.get("user", "ana") is None and repo.get("project", "ana") is not None
    assert repo.delete("user", "ana") is False


# ---------------------------------------------------------------- quem paga


def test_project_key_wins_then_user_key_then_platform():
    project = LLMProviderConfig(provider="anthropic", api_key="sk-proj")
    user = LLMProviderConfig(provider="openai", api_key="sk-user", chat_model="gpt-x")

    assert choose_llm(project, user, lambda: PLATFORM).source == "project"
    assert choose_llm(None, user, lambda: PLATFORM).source == "user"
    assert choose_llm(None, None, lambda: PLATFORM).config == PLATFORM
    # Uma chave que já não se lê (outra CREDENTIALS_SECRET_KEY) não conta.
    unreadable = LLMProviderConfig(provider="anthropic", api_key="")
    assert choose_llm(unreadable, user, lambda: PLATFORM).source == "user"


def test_own_keys_never_carry_a_custom_url():
    sneaky = LLMProviderConfig(provider="anthropic", api_key="sk", base_url="http://169.254.169.254")
    assert choose_llm(sneaky, None, lambda: PLATFORM).config.base_url == ""


def test_without_master_key_everything_uses_the_platform(monkeypatch):
    monkeypatch.setattr(dependencies, "get_secret_box", lambda: SecretBox(""))
    monkeypatch.setattr(dependencies, "active_llm_config", lambda: PLATFORM)
    monkeypatch.setattr(dependencies, "get_llm_credentials", lambda: pytest.fail("não devia ler chaves"))
    assert dependencies.resolve_llm("ana", "p1").source == "platform"


# ---------------------------------------------------------------- API


def _user(name: str) -> AuthenticatedUser:
    return AuthenticatedUser.of(User(user_id=name, username=name, roles=["chat"], created_at="x"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = sql_engine("sqlite", tmp_path)
    box = SecretBox("mestra")
    credentials = SqlLLMCredentialsRepository(engine, box)
    research = SqlResearchRepository(engine)
    research.save_project(Project(project_id="p1", owner_id="ana", title="Tese", created_at="x", updated_at="x"))
    research.set_member(ProjectMember(project_id="p1", user_id="rui", role="editor"))

    def resolve(user_id, project_id=None):
        project = credentials.get("project", project_id) if project_id else None
        return choose_llm(project, credentials.get("user", user_id), lambda: PLATFORM)

    for module in (api, dependencies):
        monkeypatch.setattr(module, "get_secret_box", lambda: box)
        monkeypatch.setattr(module, "get_llm_credentials", lambda: credentials)
    monkeypatch.setattr(api, "resolve_llm", resolve)
    monkeypatch.setattr(access, "get_research_repository", lambda: research)

    app = FastAPI()
    app.include_router(api.router)
    state = {"user": _user("ana")}
    app.dependency_overrides[current_user] = lambda: state["user"]
    http = TestClient(app)

    def as_user(name: str) -> TestClient:
        state["user"] = _user(name)
        return http

    return as_user, credentials, box


def test_personal_key_is_saved_encrypted_and_never_returned(client):
    as_user, credentials, _ = client
    http = as_user("eva")
    assert http.get("/me/llm-key").json()["effective"] == "platform"

    res = http.put("/me/llm-key", json={"provider": "anthropic", "api_key": "sk-ant-da-eva-1234"})
    assert res.status_code == 200
    state = res.json()
    assert "sk-ant-da-eva-1234" not in res.text
    assert state["key"]["key_hint"] == "…1234" and state["effective"] == "user"

    # Mudar só o modelo mantém a chave; mudar de fornecedor sem chave nova não é aceite.
    http.put("/me/llm-key", json={"provider": "anthropic", "api_key": None, "chat_model": "claude-opus-5-5"})
    assert credentials.get("user", "eva").api_key == "sk-ant-da-eva-1234"
    assert http.put("/me/llm-key", json={"provider": "openrouter", "api_key": None}).status_code == 422

    assert http.delete("/me/llm-key").json()["key"] is None


def test_personal_keys_only_accept_fixed_url_providers(client):
    as_user, credentials, _ = client
    http = as_user("eva")
    for provider in ("custom", "lmstudio", "inventado"):
        assert http.put("/me/llm-key", json={"provider": provider, "api_key": "sk"}).status_code == 422
    assert http.put("/me/llm-key", json={"provider": "openai", "api_key": "sk"}).status_code == 422  # sem modelo
    assert credentials.get("user", "eva") is None


def test_without_master_key_keys_are_not_saved(client, monkeypatch):
    as_user, credentials, _ = client
    off = SecretBox("")
    monkeypatch.setattr(api, "get_secret_box", lambda: off)
    credentials.box = off
    http = as_user("eva")
    assert http.get("/me/llm-key").json()["enabled"] is False
    res = http.put("/me/llm-key", json={"provider": "anthropic", "api_key": "sk-ant-x"})
    assert res.status_code == 503 and "CREDENTIALS_SECRET_KEY" in res.json()["detail"]


def test_only_the_owner_manages_the_project_key(client):
    as_user, credentials, _ = client
    body = {"provider": "anthropic", "api_key": "sk-ant-do-projeto-9999"}

    assert as_user("rui").put("/research/projects/p1/llm-key", json=body).status_code == 403
    assert as_user("eva").get("/research/projects/p1/llm-key").status_code == 404  # não é membro
    assert credentials.get("project", "p1") is None

    owner = as_user("ana").put("/research/projects/p1/llm-key", json=body).json()
    assert owner["can_edit"] and owner["key"]["key_hint"] == "…9999" and owner["effective"] == "project"

    member = as_user("rui").get("/research/projects/p1/llm-key").json()
    assert member["key"]["provider"] == "anthropic" and member["key"]["key_hint"] == ""
    assert not member["can_edit"] and member["effective"] == "project"

    assert as_user("rui").delete("/research/projects/p1/llm-key").status_code == 403
    assert as_user("ana").delete("/research/projects/p1/llm-key").json()["effective"] == "platform"


def test_project_key_beats_the_members_own_key(client):
    as_user, _, _ = client
    as_user("rui").put("/me/llm-key", json={"provider": "openrouter", "api_key": "sk-or-do-rui"})
    assert as_user("rui").get("/research/projects/p1/llm-key").json()["effective"] == "user"
    as_user("ana").put("/research/projects/p1/llm-key", json={"provider": "anthropic", "api_key": "sk-ant-proj"})
    assert as_user("rui").get("/research/projects/p1/llm-key").json()["effective"] == "project"


def test_pipeline_for_answers_with_the_request_key_without_touching_the_shared_one(monkeypatch):
    class Pipeline:
        lmstudio_client = "cliente da plataforma"

    shared = Pipeline()
    user_key = LLMProviderConfig(provider="anthropic", api_key="sk-ant-da-ana")
    monkeypatch.setattr(dependencies, "get_rag_pipeline", lambda: shared)
    monkeypatch.setattr(dependencies, "resolve_llm", lambda user_id, project_id=None: choose_llm(None, user_key, lambda: PLATFORM))

    pipeline = dependencies.pipeline_for("ana")
    assert pipeline is not shared and shared.lmstudio_client == "cliente da plataforma"
    assert pipeline.lmstudio_client.model == "claude-sonnet-5-5"
    assert dependencies.llm_for("ana", role="utility").model == "claude-haiku-5-5"
