"""Fornecedor de LLM configurado na aplicação: repositório, cliente por fornecedor e API /settings/llm."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import llm_settings as api
from backend.api.security import current_user
from backend.auth.permissions import AuthenticatedUser
from backend.config import Settings
from backend.models import LLMProviderConfig, User
from backend.repositories.sql import SqlLLMSettingsRepository
from backend.services.llm_providers import ConfigurableLLM, build_client, env_fallback
from tests.repository_fixtures import SQL_BACKENDS, sql_engine


@pytest.fixture(params=SQL_BACKENDS)
def repo(request, tmp_path):
    return SqlLLMSettingsRepository(sql_engine(request.param, tmp_path))


def test_only_one_provider_is_active(repo):
    assert repo.get_active() is None
    repo.save(LLMProviderConfig(provider="openrouter", api_key="sk-or-1", active=True))
    repo.save(LLMProviderConfig(provider="anthropic", api_key="sk-ant-1", chat_model="claude-x", active=True))

    assert repo.get_active().provider == "anthropic"
    assert repo.get("openrouter").active is False
    assert repo.get("openrouter").api_key == "sk-or-1"
    assert [c.provider for c in repo.list_providers()] == ["anthropic", "openrouter"]

    repo.save(LLMProviderConfig(provider="anthropic", api_key="sk-ant-2", chat_model="claude-y", active=True))
    assert repo.get("anthropic").api_key == "sk-ant-2"
    assert len(repo.list_providers()) == 2


def test_anthropic_client_uses_defaults_headers_and_token_limit():
    client = build_client(LLMProviderConfig(provider="anthropic", api_key="sk-ant-123"), role="utility")
    assert client.base_url == "https://api.anthropic.com/v1"
    assert client.model == "claude-haiku-5-5"
    assert client.max_tokens
    assert client.headers["x-api-key"] == "sk-ant-123"
    assert client.headers["Authorization"] == "Bearer sk-ant-123"
    assert "anthropic-version" in client.headers
    # Os modelos Claude atuais devolvem 400 se o pedido levar temperature.
    assert "temperature" not in client._temperature(0.2)
    assert build_client(LLMProviderConfig(provider="openrouter", api_key="k"))._temperature(0.2)["temperature"] == 0.2


def test_utility_role_falls_back_to_chat_model():
    config = LLMProviderConfig(provider="lmstudio", chat_model="qwen")
    assert build_client(config, "utility").model == "qwen"
    assert build_client(config, "utility").headers == {}


def test_env_fallback_keeps_previous_behaviour():
    with_key = env_fallback(Settings(_env_file=None, open_router_api_key="sk-or-env"))
    assert (with_key.provider, with_key.api_key) == ("openrouter", "sk-or-env")
    assert env_fallback(Settings(_env_file=None, open_router_api_key="")).provider == "lmstudio"


def test_configurable_llm_follows_the_active_provider():
    current = {"config": LLMProviderConfig(provider="openrouter", api_key="k", active=True)}
    llm = ConfigurableLLM(lambda: current["config"], role="chat")
    assert llm.model == "anthropic/claude-sonnet-5.5"
    current["config"] = LLMProviderConfig(provider="anthropic", api_key="k", active=True)
    assert llm.model == "claude-sonnet-5-5"


@pytest.fixture
def client(monkeypatch, tmp_path):
    repo = SqlLLMSettingsRepository(sql_engine("sqlite", tmp_path))
    env = LLMProviderConfig(provider="openrouter", api_key="sk-or-from-env-1234", chat_model="m", active=True)
    monkeypatch.setattr(api, "get_llm_settings", lambda: repo)
    monkeypatch.setattr(api, "active_llm_config", lambda: repo.get_active() or env)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[current_user] = lambda: _user("admin")
    http = TestClient(app)
    http.app_ref = app
    return http, repo


def _user(role: str) -> AuthenticatedUser:
    return AuthenticatedUser.of(User(user_id=role, username=role, roles=[role], created_at="x"))


def test_only_admins_manage_llm_providers(client):
    http, repo = client
    http.app_ref.dependency_overrides[current_user] = lambda: _user("manager")
    assert http.get("/settings/llm").status_code == 403
    assert http.put("/settings/llm/anthropic", json={"api_key": "sk-ant-1"}).status_code == 403
    assert http.post("/settings/llm/anthropic/test", json={"api_key": "sk-ant-1"}).status_code == 403
    assert repo.get("anthropic") is None


def test_state_starts_from_env_and_never_returns_keys(client):
    http, _ = client
    state = http.get("/settings/llm").json()
    assert (state["active"], state["source"]) == ("openrouter", "env")
    openrouter = next(p for p in state["providers"] if p["id"] == "openrouter")
    assert openrouter["has_key"] and openrouter["key_hint"] == "…1234"
    assert "sk-or-from-env-1234" not in str(state)


def test_save_activates_and_keeps_key_when_omitted(client):
    http, repo = client
    res = http.put("/settings/llm/anthropic", json={"api_key": "sk-ant-secret-9999"})
    assert res.status_code == 200
    assert (res.json()["active"], res.json()["source"]) == ("anthropic", "database")
    assert "sk-ant-secret-9999" not in res.text

    http.put("/settings/llm/anthropic", json={"chat_model": "claude-opus-5-5"})
    saved = repo.get("anthropic")
    assert (saved.api_key, saved.chat_model) == ("sk-ant-secret-9999", "claude-opus-5-5")


def test_first_save_of_env_provider_inherits_env_key(client):
    http, repo = client
    assert http.put("/settings/llm/openrouter", json={"chat_model": "openai/gpt-x"}).status_code == 200
    assert repo.get("openrouter").api_key == "sk-or-from-env-1234"


def test_save_without_activate_keeps_current_provider(client):
    http, repo = client
    http.put("/settings/llm/anthropic", json={"api_key": "sk-ant-1"})
    http.put("/settings/llm/openai", json={"api_key": "sk-oa-1", "chat_model": "gpt", "activate": False})
    assert repo.get_active().provider == "anthropic"


def test_validation(client):
    http, _ = client
    assert http.put("/settings/llm/anthropic", json={}).status_code == 422  # sem chave
    assert http.put("/settings/llm/custom", json={"chat_model": "m"}).status_code == 422  # sem URL
    assert http.put("/settings/llm/openai", json={"api_key": "k"}).status_code == 422  # sem modelo
    assert http.put("/settings/llm/nope", json={}).status_code == 404


def test_test_endpoint_reports_provider_errors(client, monkeypatch):
    http, repo = client

    def fake_ping(self):
        if self.model == "claude-haiku-5-5":
            raise RuntimeError("HTTP 404: model not found")

    monkeypatch.setattr("backend.services.lmstudio_client.LMStudioClient.ping", fake_ping)
    body = http.post("/settings/llm/anthropic/test", json={"api_key": "sk-ant-1"}).json()
    assert body["ok"] is False
    assert body["results"]["chat"]["ok"] is True
    assert "404" in body["results"]["utility"]["error"]
    assert repo.get("anthropic") is None  # testar não guarda
