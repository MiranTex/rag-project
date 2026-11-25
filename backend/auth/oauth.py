"""Servidor de autorização OAuth 2.1 do servidor MCP, para quem não sabe (nem precisa de saber) o que é um token:
no claude.ai, no Claude Desktop ou no Claude Code basta pôr o endereço do /mcp; a aplicação abre esta plataforma no
browser, a pessoa entra com a conta de sempre e autoriza.

O protocolo (metadados, registo dinâmico de clientes, /authorize, /token com PKCE, /revoke) é o do SDK MCP
(mcp.server.auth); aqui fica só o que é desta aplicação, o "provider":

1. /authorize valida o pedido e chama authorize(): guarda o pedido (10 minutos) e manda a pessoa para a página de
   consentimento da interface (PUBLIC_APP_URL/ligar/autorizar?pedido=…).
2. Na interface, com a sessão normal, a pessoa vê que aplicação pede acesso e autoriza (só ler, ou ler e propor)
   ou recusa (api/oauth_consent.py → approve/deny). Ao autorizar fica uma autorização (grant) e um código de 5
   minutos, devolvido à aplicação no redirect_uri.
3. A aplicação troca o código por um token de acesso (1 hora) e um de renovação (30 dias, trocado a cada uso).

Tokens, códigos e pedidos guardam-se só como SHA-256. Revogar a autorização na conta apaga todos os tokens dela."""

import hashlib
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import anyio
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from backend.auth.access_tokens import READ, WRITE
from backend.auth.authenticators import AuthError
from backend.models import OAuthGrant, OAuthTokenRecord, User
from backend.repositories.contracts import OAuthRepository, UserRepository

ACCESS_PREFIX = "rag_oat_"
REFRESH_PREFIX = "rag_ort_"
SCOPES = [READ, WRITE]
REQUEST_SECONDS = 10 * 60
CODE_SECONDS = 5 * 60
ACCESS_SECONDS = 60 * 60
REFRESH_SECONDS = 30 * 24 * 60 * 60
TOUCH_EVERY = timedelta(minutes=5)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def client_label(info: dict | OAuthClientInformationFull | None) -> str:
    """Nome a mostrar de uma aplicação (o que ela diz de si no registo)."""
    if info is None:
        return "Aplicação desconhecida"
    name = info.get("client_name") if isinstance(info, dict) else info.client_name
    return (name or "Aplicação sem nome").strip()[:120]


class OAuthProvider:
    """Implementa mcp.server.auth.provider.OAuthAuthorizationServerProvider sobre o OAuthRepository."""

    def __init__(self, repo: Callable[[], OAuthRepository], users: Callable[[], UserRepository], app_url: str) -> None:
        # Fábricas, e não os repositórios: a app cria o provider ao arrancar, antes de haver base de dados.
        self._repo = repo
        self._users = users
        self.app_url = app_url.rstrip("/")

    @property
    def repo(self) -> OAuthRepository:
        return self._repo()

    @property
    def users(self) -> UserRepository:
        return self._users()

    # ---- Clientes ----

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        info = await anyio.to_thread.run_sync(self.repo.get_client, client_id)
        return OAuthClientInformationFull.model_validate(info) if info else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await anyio.to_thread.run_sync(self.repo.save_client, client_info.client_id, client_info.model_dump(mode="json"))

    # ---- Pedido de autorização → consentimento na interface ----

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        request_id = secrets.token_urlsafe(24)
        scopes = params.scopes or (client.scope.split() if client.scope else [READ])
        record = OAuthTokenRecord(
            token_hash=_hash(request_id),
            kind="request",
            client_id=client.client_id,
            scopes=" ".join(s for s in SCOPES if s in scopes) or READ,
            expires_at=time.time() + REQUEST_SECONDS,
            data={
                "state": params.state,
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource,
            },
        )

        def save() -> None:
            self.repo.delete_expired(time.time())
            self.repo.save_token(record)

        await anyio.to_thread.run_sync(save)
        return f"{self.app_url}/ligar/autorizar?pedido={request_id}"

    def pending_request(self, request_id: str) -> tuple[OAuthTokenRecord, dict] | None:
        """O pedido à espera de consentimento e a aplicação que o fez; None se não existe ou expirou."""
        record = self.repo.get_token(_hash(request_id), "request")
        if record is None or record.expires_at < time.time():
            return None
        return record, self.repo.get_client(record.client_id) or {}

    def approve(self, request_id: str, user: User, scopes: list[str]) -> str:
        """A pessoa autorizou: cria (ou atualiza) a autorização e devolve o redirect com o código."""
        pending = self.pending_request(request_id)
        if pending is None:
            raise AuthError("O pedido de autorização expirou. Volta a ligar a aplicação.")
        record, _ = pending
        granted = [s for s in SCOPES if s in scopes and s in record.scopes.split()] or [READ]
        grant = self.repo.find_grant(user.user_id, record.client_id)
        grant = (grant or OAuthGrant(grant_id=str(uuid4()), user_id=user.user_id, client_id=record.client_id, scopes="", created_at=_now_iso()))
        grant = grant.model_copy(update={"scopes": " ".join(granted)})
        self.repo.save_grant(grant)
        code = secrets.token_urlsafe(32)
        self.repo.save_token(
            OAuthTokenRecord(
                token_hash=_hash(code),
                kind="code",
                grant_id=grant.grant_id,
                client_id=record.client_id,
                user_id=user.user_id,
                scopes=grant.scopes,
                expires_at=time.time() + CODE_SECONDS,
                data=record.data,
            )
        )
        self.repo.delete_token(record.token_hash)
        return construct_redirect_uri(record.data["redirect_uri"], code=code, state=record.data.get("state"))

    def deny(self, request_id: str) -> str:
        pending = self.pending_request(request_id)
        if pending is None:
            raise AuthError("O pedido de autorização expirou.")
        record, _ = pending
        self.repo.delete_token(record.token_hash)
        return construct_redirect_uri(
            record.data["redirect_uri"],
            error="access_denied",
            error_description="A pessoa recusou o acesso.",
            state=record.data.get("state"),
        )

    # ---- Código → tokens ----

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> AuthorizationCode | None:
        record = await anyio.to_thread.run_sync(self.repo.get_token, _hash(authorization_code), "code")
        if record is None or record.client_id != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=record.scopes.split(),
            expires_at=record.expires_at,
            client_id=record.client_id,
            code_challenge=record.data["code_challenge"],
            redirect_uri=record.data["redirect_uri"],
            redirect_uri_provided_explicitly=record.data["redirect_uri_provided_explicitly"],
            resource=record.data.get("resource"),
            subject=record.user_id,
        )

    def _issue(self, grant_id: str, client_id: str, user_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        access, refresh = ACCESS_PREFIX + secrets.token_urlsafe(32), REFRESH_PREFIX + secrets.token_urlsafe(32)
        now = time.time()
        for token, kind, seconds in ((access, "access", ACCESS_SECONDS), (refresh, "refresh", REFRESH_SECONDS)):
            self.repo.save_token(
                OAuthTokenRecord(
                    token_hash=_hash(token),
                    kind=kind,
                    grant_id=grant_id,
                    client_id=client_id,
                    user_id=user_id,
                    scopes=" ".join(scopes),
                    expires_at=now + seconds,
                    data={"resource": resource},
                )
            )
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_SECONDS, scope=" ".join(scopes), refresh_token=refresh)

    def _redeem(self, token: str, kind: str) -> OAuthTokenRecord:
        """Gasta um código ou token de renovação (só uma vez) e confirma que a autorização ainda existe."""
        record = self.repo.get_token(_hash(token), kind)
        if record is None or not self.repo.delete_token(record.token_hash):
            raise TokenError("invalid_grant", "Código ou token já usado ou revogado.")
        grant = self.repo.get_grant(record.grant_id or "")
        if grant is None:
            raise TokenError("invalid_grant", "A autorização foi revogada.")
        return record

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        def run() -> OAuthToken:
            record = self._redeem(authorization_code.code, "code")
            return self._issue(record.grant_id, client.client_id, record.user_id, authorization_code.scopes, authorization_code.resource)

        return await anyio.to_thread.run_sync(run)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        record = await anyio.to_thread.run_sync(self.repo.get_token, _hash(refresh_token), "refresh")
        if record is None or record.client_id != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=record.client_id,
            scopes=record.scopes.split(),
            expires_at=int(record.expires_at),
            resource=record.data.get("resource"),
            subject=record.user_id,
        )

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        def run() -> OAuthToken:
            record = self._redeem(refresh_token.token, "refresh")
            grant = self.repo.get_grant(record.grant_id)
            # Nunca mais do que a autorização tem agora (pode ter sido reduzida).
            allowed = [s for s in (scopes or refresh_token.scopes) if s in grant.scopes.split()] or [READ]
            return self._issue(grant.grant_id, client.client_id, record.user_id, allowed, refresh_token.resource)

        return await anyio.to_thread.run_sync(run)

    # ---- Uso e revogação ----

    async def load_access_token(self, token: str) -> AccessToken | None:
        record = await anyio.to_thread.run_sync(self.repo.get_token, _hash(token), "access")
        if record is None or record.expires_at < time.time():
            return None
        return AccessToken(
            token=token,
            client_id=record.client_id,
            scopes=record.scopes.split(),
            expires_at=int(record.expires_at),
            resource=record.data.get("resource"),
            subject=record.user_id,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await anyio.to_thread.run_sync(self.repo.delete_token, _hash(token.token))

    def authenticate(self, token: str) -> tuple[User, str, list[str]]:
        """Para o /mcp: a pessoa, o nome da aplicação (assina o que ela escreve) e o que pode fazer."""
        record = self.repo.get_token(_hash(token), "access")
        if record is None or record.expires_at < time.time():
            raise AuthError("Token OAuth inválido ou expirado.")
        grant = self.repo.get_grant(record.grant_id or "")
        user = self.users.find_by_id(record.user_id or "")
        if grant is None or user is None or not user.active:
            raise AuthError("Autorização revogada ou utilizador desativado.")
        now = datetime.now(UTC)
        if grant.last_used_at is None or now - datetime.fromisoformat(grant.last_used_at) > TOUCH_EVERY:
            self.repo.touch_grant(grant.grant_id, now.isoformat())
        return user, client_label(self.repo.get_client(record.client_id)), record.scopes.split()
