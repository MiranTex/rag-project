import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.settings as settings_api
from backend import config
from backend.api.security import current_user
from backend.auth.permissions import AuthenticatedUser
from backend.models import User
from backend.repositories.sql import SqlSettingsRepository
from backend.settings_catalog import CATALOG, validate_setting
from tests.repository_fixtures import SQL_BACKENDS, sql_engine


@pytest.fixture
def overrides():
    """Configurações guardadas num dicionário, ligadas a get_settings() só durante o teste."""
    stored: dict = {}
    config.install_settings_source(lambda: dict(stored))
    yield stored
    config.install_settings_source(None)


@pytest.mark.parametrize(
    "key, value, expected",
    [
        ("top_k", 6, 6),
        ("top_k", "6", 6),
        ("guard_enabled", False, False),
        ("retrieval_mode_default", "vector", "vector"),
        ("review_max_garbled_ratio", 0.3, 0.3),
        ("knowledge_base_description", "  Contratos da empresa.  ", "Contratos da empresa."),
        ("rerank_weights_default", '{"vector": 1, "keyword": 0.5}', json.dumps({"vector": 1.0, "keyword": 0.5})),
        ("rerank_weights_default", {"vector": 2}, json.dumps({"vector": 2.0})),
    ],
)
def test_valid_values_are_normalised(key, value, expected):
    assert validate_setting(key, value) == expected


@pytest.mark.parametrize(
    "key, value",
    [
        ("top_k", 0),
        ("top_k", 21),
        ("top_k", True),
        ("top_k", "muitos"),
        ("guard_enabled", "talvez"),
        ("retrieval_mode_default", "magia"),
        ("review_max_garbled_ratio", 1.5),
        ("knowledge_base_description", "   "),
        ("rerank_weights_default", "não é json"),
        ("rerank_weights_default", {"vector": -1}),
        ("rerank_weights_default", {"sorte": 1}),
        ("rerank_weights_default", {"vector": 0}),
        ("database_url", "sqlite:///outra.db"),
    ],
)
def test_invalid_values_and_infrastructure_settings_are_rejected(key, value):
    with pytest.raises(ValueError):
        validate_setting(key, value)


def test_every_catalog_entry_is_a_real_setting():
    assert all(entry.key in config.Settings.model_fields for entry in CATALOG)


@pytest.mark.parametrize("backend", SQL_BACKENDS)
def test_settings_repository_contract(backend, tmp_path):
    repo = SqlSettingsRepository(sql_engine(backend, tmp_path))
    assert repo.load() == {}

    repo.save({"top_k": 6, "guard_enabled": False}, "u1")
    repo.save({"top_k": 8}, "u2")
    assert repo.load() == {"top_k": 8, "guard_enabled": False}

    assert repo.delete("top_k") is True and repo.delete("top_k") is False
    assert repo.load() == {"guard_enabled": False}


def test_saved_settings_override_the_env_and_rebuild_cached_services(overrides):
    rebuilt = []
    config.on_settings_change(lambda: rebuilt.append(True))
    try:
        env_top_k = config.get_env_settings().top_k
        assert config.get_settings().top_k == env_top_k

        overrides["top_k"] = env_top_k + 3
        # Dentro do intervalo de releitura continua o valor anterior; refresh_settings relê já.
        assert config.get_settings().top_k == env_top_k
        assert config.refresh_settings().top_k == env_top_k + 3
        assert rebuilt == [True]

        # Sem mudanças não recria nada.
        config.refresh_settings()
        assert rebuilt == [True]
    finally:
        config._change_listeners.pop()


def test_unreadable_settings_keep_the_last_good_values():
    database = {"up": True}

    def source():
        if not database["up"]:
            raise ConnectionError("base de dados em baixo")
        return {"top_k": 9}

    config.install_settings_source(source)
    try:
        assert config.refresh_settings().top_k == 9
        database["up"] = False
        assert config.refresh_settings().top_k == 9
    finally:
        config.install_settings_source(None)


@pytest.fixture
def api(tmp_path, monkeypatch):
    repo = SqlSettingsRepository(sql_engine("sqlite", tmp_path))
    monkeypatch.setattr(settings_api, "get_settings_repository", lambda: repo)
    config.install_settings_source(repo.load)
    state = {"user": AuthenticatedUser.of(User(user_id="adm", username="adm", roles=["admin"], created_at="x"))}
    app = FastAPI()
    app.include_router(settings_api.router)
    app.dependency_overrides[current_user] = lambda: state["user"]
    state["client"], state["repo"] = TestClient(app), repo
    yield state
    config.install_settings_source(None)


def _by_key(items):
    return {item["key"]: item for item in items}


def test_admin_changes_and_resets_settings(api):
    client = api["client"]
    before = _by_key(client.get("/settings").json())
    assert before["top_k"]["overridden"] is False
    assert before["top_k"]["value"] == before["top_k"]["default"]

    res = client.put("/settings", json={"values": {"top_k": 7, "guard_enabled": False}})
    assert res.status_code == 200, res.text
    after = _by_key(res.json())
    assert (after["top_k"]["value"], after["top_k"]["overridden"]) == (7, True)
    assert after["guard_enabled"]["value"] is False
    assert config.get_settings().top_k == 7

    reset = _by_key(client.delete("/settings/top_k").json())
    assert (reset["top_k"]["value"], reset["top_k"]["overridden"]) == (before["top_k"]["default"], False)


def test_invalid_update_saves_nothing(api):
    res = api["client"].put("/settings", json={"values": {"top_k": 7, "retrieval_mode_default": "magia"}})
    assert res.status_code == 422
    assert api["repo"].load() == {}


def test_only_admins_manage_settings(api):
    api["user"] = AuthenticatedUser.of(User(user_id="g", username="g", roles=["manager"], created_at="x"))
    assert api["client"].get("/settings").status_code == 403
    assert api["client"].put("/settings", json={"values": {"top_k": 7}}).status_code == 403
