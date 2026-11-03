from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.auth as auth_api
import backend.api.chat as chat_api
import backend.api.exports as exports_api
import backend.api.security as security
import backend.api.users as users_api
from backend.auth.authenticators import (
    AuthError,
    ExternalAuthenticator,
    LocalAuthenticator,
    create_local_user,
    ensure_bootstrap_admin,
)
from backend.auth.passwords import hash_password, verify_password
from backend.auth.permissions import CHAT_USE, DOCUMENTS_APPROVE, DOCUMENTS_UPLOAD, permissions_for
from backend.config import Settings
from backend.models import User
from backend.repositories.sql import SqlUserRepository
from backend.services.export_store import ExportStore
from tests.repository_fixtures import SQL_BACKENDS, sql_engine

SECRET = "segredo-de-teste-com-tamanho-suficiente"


@pytest.fixture
def users(tmp_path):
    return SqlUserRepository(sql_engine("sqlite", tmp_path))


def _token(claims: dict, key=SECRET, algorithm="HS256", minutes=5) -> str:
    return jwt.encode({"exp": datetime.now(UTC) + timedelta(minutes=minutes), **claims}, key, algorithm=algorithm)


def test_passwords_are_salted_and_verified():
    first, second = hash_password("palavra-passe"), hash_password("palavra-passe")
    assert first != second
    assert verify_password("palavra-passe", first)
    assert not verify_password("outra", first)
    assert not verify_password("palavra-passe", "") and not verify_password("palavra-passe", "lixo")


def test_permissions_are_the_union_of_the_roles():
    assert permissions_for(["chat"]) == {CHAT_USE}
    uploader_and_reviewer = permissions_for(["uploader", "reviewer"])
    assert {DOCUMENTS_UPLOAD, DOCUMENTS_APPROVE} <= uploader_and_reviewer
    assert permissions_for(["desconhecido"]) == frozenset()


@pytest.mark.parametrize("backend", SQL_BACKENDS)
def test_user_repository_contract(backend, tmp_path):
    users = SqlUserRepository(sql_engine(backend, tmp_path))
    user = User(user_id="u1", username="ana", display_name="Ana", roles=["manager"], created_at="2026-11-03")
    users.add_or_replace(user)
    users.set_password_hash("u1", "hash")

    assert users.find_by_id("u1") == user and users.find_by_username("ana") == user
    assert users.password_hash("u1") == "hash"
    # Gravar o utilizador de novo não toca na palavra-passe.
    users.add_or_replace(user.model_copy(update={"roles": ["chat"], "active": False}))
    assert users.find_by_id("u1").roles == ["chat"] and users.password_hash("u1") == "hash"

    external = User(user_id="u2", username="rui", external_id="sub-rui", created_at="2026-11-03")
    users.add_or_replace(external)
    assert users.find_by_external_id("sub-rui") == external
    assert [u.username for u in users.list_users()] == ["ana", "rui"] and users.count() == 2
    assert users.find_by_id("nope") is None and users.password_hash("nope") == ""


def test_local_login_and_token(users):
    user = create_local_user(users, "ana", "palavra-passe", ["manager"])
    auth = LocalAuthenticator(users, SECRET, token_minutes=5)

    assert auth.login("ana", "palavra-passe") == user
    token, expires_in = auth.issue(user)
    assert expires_in == 300 and auth.authenticate(token) == user

    for username, password in [("ana", "errada"), ("ninguem", "palavra-passe")]:
        with pytest.raises(AuthError):
            auth.login(username, password)
    with pytest.raises(AuthError):
        auth.authenticate(_token({"sub": user.user_id, "iss": "rag-local"}, minutes=-1))
    with pytest.raises(AuthError):
        auth.authenticate(_token({"sub": user.user_id, "iss": "outro"}))

    # Desativado: nem login nem tokens já emitidos.
    users.add_or_replace(user.model_copy(update={"active": False}))
    with pytest.raises(AuthError):
        auth.login("ana", "palavra-passe")
    with pytest.raises(AuthError):
        auth.authenticate(token)


def test_bootstrap_admin_only_when_there_are_no_users(users):
    settings = Settings(_env_file=None, auth_bootstrap_admin_username="admin", auth_bootstrap_admin_password="palavra-passe")
    ensure_bootstrap_admin(settings, users)
    ensure_bootstrap_admin(settings, users)

    [admin] = users.list_users()
    assert admin.roles == ["admin"]
    assert LocalAuthenticator(users, SECRET, 5).login("admin", "palavra-passe") == admin


def test_external_user_is_created_on_first_access_with_default_roles(users):
    auth = ExternalAuthenticator(users, secret=SECRET, algorithms=["HS256"], issuer="https://sso", default_roles=["chat"])
    token = _token({"sub": "abc", "iss": "https://sso", "preferred_username": "rui", "name": "Rui Silva"})

    user = auth.authenticate(token)
    assert (user.username, user.display_name, user.roles, user.external_id) == ("rui", "Rui Silva", ["chat"], "abc")
    # Segundo acesso: o mesmo utilizador; os papéis atribuídos cá dentro mantêm-se.
    users.add_or_replace(user.model_copy(update={"roles": ["manager"]}))
    assert auth.authenticate(token).roles == ["manager"]

    with pytest.raises(AuthError):
        auth.authenticate(_token({"sub": "abc", "iss": "https://outro"}))
    with pytest.raises(AuthError):
        auth.authenticate(_token({"sub": "abc", "iss": "https://sso"}, key="chave-errada-com-tamanho-suficiente"))


def test_external_roles_come_from_the_token_when_configured(users):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    auth = ExternalAuthenticator(
        users,
        public_key=public_pem,
        algorithms=["RS256"],
        audience="rag",
        roles_claim="groups",
        role_map={"rag-gestores": "manager"},
    )

    def token(groups):
        return _token({"sub": "abc", "aud": "rag", "groups": groups}, key=private_key, algorithm="RS256")

    assert auth.authenticate(token(["rag-gestores", "outro-grupo"])).roles == ["manager"]
    # O grupo saiu no sistema externo: o papel sai também.
    assert auth.authenticate(token(["outro-grupo"])).roles == []
    with pytest.raises(AuthError):
        auth.authenticate(_token({"sub": "abc", "aud": "outra-app"}, key=private_key, algorithm="RS256"))


class _FakePipeline:
    def ask(self, **kwargs):
        return "resposta", []


@pytest.fixture
def api(users, tmp_path, monkeypatch):
    settings = Settings(_env_file=None)
    authenticator = LocalAuthenticator(users, SECRET, 5)
    exports = ExportStore(tmp_path / "exports")
    for module in (auth_api, users_api):
        monkeypatch.setattr(module, "get_users", lambda: users)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api, "get_authenticator", lambda: authenticator)
    monkeypatch.setattr(security, "get_authenticator", lambda: authenticator)
    monkeypatch.setattr(exports_api, "get_export_store", lambda: exports)
    monkeypatch.setattr(chat_api, "get_rag_pipeline", lambda: _FakePipeline())
    monkeypatch.setattr(chat_api, "get_settings", lambda: settings)

    app = FastAPI()
    for module in (auth_api, users_api, exports_api, chat_api):
        app.include_router(module.router)
    client = TestClient(app)
    create_local_user(users, "admin", "palavra-passe", ["admin"])

    def login(username, password="palavra-passe"):
        res = client.post("/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return {"client": client, "login": login, "exports": exports, "users": users}


def test_requests_without_a_valid_session_are_rejected(api):
    client = api["client"]
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer lixo"}).status_code == 401
    assert client.post("/auth/login", json={"username": "admin", "password": "errada"}).status_code == 401
    assert client.get("/auth/config").json() == {"mode": "local", "roles_from_token": False}


def test_admin_creates_a_chat_user_who_only_uses_the_chat(api):
    client, admin = api["client"], api["login"]("admin")
    res = client.post("/users", headers=admin, json={"username": "leitor", "password": "palavra-passe", "roles": ["chat"]})
    assert res.status_code == 200, res.text
    assert client.post("/users", headers=admin, json={"username": "leitor", "password": "palavra-passe"}).status_code == 409
    assert client.post("/users", headers=admin, json={"username": "x", "password": "palavra-passe", "roles": ["chefe"]}).status_code == 422

    reader = api["login"]("leitor")
    assert client.get("/auth/me", headers=reader).json()["permissions"] == [CHAT_USE]
    assert client.get("/users", headers=reader).status_code == 403
    assert client.post("/chat/ask", headers=reader, json={"question": "Qual é o prazo?"}).json()["answer"] == "resposta"
    # Pode perguntar, mas não restringir a pergunta a um documento.
    res = client.post("/chat/ask", headers=reader, json={"question": "Qual é o prazo?", "document_id": "d1"})
    assert res.status_code == 403


def test_admin_cannot_lock_themselves_out(api):
    client, admin = api["client"], api["login"]("admin")
    admin_id = client.get("/auth/me", headers=admin).json()["user"]["user_id"]

    assert client.patch(f"/users/{admin_id}", headers=admin, json={"active": False}).status_code == 400
    assert client.patch(f"/users/{admin_id}", headers=admin, json={"roles": ["manager"]}).status_code == 400
    assert client.patch(f"/users/{admin_id}", headers=admin, json={"display_name": "Chefe"}).json()["display_name"] == "Chefe"


def test_deactivated_user_loses_the_session_and_password_change(api):
    client, admin = api["client"], api["login"]("admin")
    user_id = client.post(
        "/users", headers=admin, json={"username": "ana", "password": "palavra-passe", "roles": ["manager"]}
    ).json()["user_id"]
    ana = api["login"]("ana")

    res = client.put("/auth/password", headers=ana, json={"current_password": "errada", "new_password": "nova-palavra"})
    assert res.status_code == 400
    res = client.put("/auth/password", headers=ana, json={"current_password": "palavra-passe", "new_password": "nova-palavra"})
    assert res.status_code == 200
    api["login"]("ana", "nova-palavra")

    client.patch(f"/users/{user_id}", headers=admin, json={"active": False})
    assert client.get("/auth/me", headers=ana).status_code == 401


def test_exports_are_visible_only_to_who_created_them(api):
    client, admin = api["client"], api["login"]("admin")
    client.post("/users", headers=admin, json={"username": "ana", "password": "palavra-passe", "roles": ["chat"]})
    ana = api["login"]("ana")
    ana_id = client.get("/auth/me", headers=ana).json()["user"]["user_id"]

    path = api["exports"].for_owner(ana_id).reserve_path("resumo", "md")
    path.write_text("# Resumo")

    assert [e["name"] for e in client.get("/exports", headers=ana).json()] == ["resumo.md"]
    assert client.get("/exports/resumo.md", headers=ana).text == "# Resumo"
    assert client.get("/exports", headers=admin).json() == []
    assert client.get("/exports/resumo.md", headers=admin).status_code == 404
