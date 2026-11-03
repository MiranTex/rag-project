"""Autenticação por token Bearer, com duas implementações escolhidas por AUTH_MODE:

- local: a própria aplicação guarda utilizadores e palavras-passe e emite os tokens (standalone);
- external: os tokens vêm de outro sistema (SSO/OIDC) e só se validam aqui; o utilizador é criado no primeiro
  acesso e os papéis vêm do token (AUTH_EXTERNAL_ROLES_CLAIM) ou são geridos nesta aplicação.

O resto do código só vê o User devolvido por authenticate()."""

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

import jwt

from backend.auth.passwords import hash_password, verify_password
from backend.auth.permissions import ROLES
from backend.config import Settings
from backend.models import User
from backend.repositories.contracts import UserRepository

logger = logging.getLogger(__name__)

# Comparado quando o utilizador não existe, para o login demorar o mesmo nos dois casos.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


class AuthError(Exception):
    """Token ou credenciais inválidos (a mensagem pode ser mostrada ao utilizador)."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Authenticator(Protocol):
    mode: str

    def authenticate(self, token: str) -> User: ...


class LocalAuthenticator:
    mode = "local"
    ISSUER = "rag-local"
    ALGORITHM = "HS256"

    def __init__(self, users: UserRepository, secret: str, token_minutes: int) -> None:
        self.users = users
        self.secret = secret
        self.token_minutes = token_minutes

    def issue(self, user: User) -> tuple[str, int]:
        """Token para o utilizador e a validade em segundos."""
        expires_in = self.token_minutes * 60
        now = datetime.now(UTC)
        claims = {"sub": user.user_id, "iss": self.ISSUER, "iat": now, "exp": now + timedelta(seconds=expires_in)}
        return jwt.encode(claims, self.secret, algorithm=self.ALGORITHM), expires_in

    def login(self, username: str, password: str) -> User:
        user = self.users.find_by_username(username)
        stored = self.users.password_hash(user.user_id) if user else ""
        valid = verify_password(password, stored or _DUMMY_HASH)
        if not (user and stored and valid and user.active):
            raise AuthError("Utilizador ou palavra-passe inválidos.")
        return user

    def authenticate(self, token: str) -> User:
        try:
            claims = jwt.decode(
                token, self.secret, algorithms=[self.ALGORITHM], issuer=self.ISSUER, options={"require": ["exp", "sub"]}
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError("Sessão inválida ou expirada.") from exc
        user = self.users.find_by_id(claims["sub"])
        if user is None or not user.active:
            raise AuthError("Utilizador inexistente ou desativado.")
        return user


class ExternalAuthenticator:
    mode = "external"

    def __init__(
        self,
        users: UserRepository,
        *,
        jwks_url: str = "",
        public_key: str = "",
        secret: str = "",
        algorithms: list[str],
        issuer: str = "",
        audience: str = "",
        username_claim: str = "preferred_username",
        name_claim: str = "name",
        roles_claim: str = "",
        role_map: dict[str, str] | None = None,
        default_roles: list[str] | None = None,
    ) -> None:
        if not (jwks_url or public_key or secret):
            raise ValueError("AUTH_MODE=external precisa de AUTH_EXTERNAL_JWKS_URL, _PUBLIC_KEY ou _SECRET.")
        self.users = users
        self.jwks = jwt.PyJWKClient(jwks_url) if jwks_url else None
        self.static_key = public_key or secret
        self.algorithms = algorithms
        self.issuer = issuer
        self.audience = audience
        self.username_claim = username_claim
        self.name_claim = name_claim
        self.roles_claim = roles_claim
        self.role_map = role_map or {}
        self.default_roles = default_roles or []

    def _claims(self, token: str) -> dict:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key if self.jwks else self.static_key
            return jwt.decode(
                token,
                key,
                algorithms=self.algorithms,
                issuer=self.issuer or None,
                audience=self.audience or None,
                options={"require": ["exp", "sub"], "verify_aud": bool(self.audience)},
            )
        except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
            raise AuthError("Token inválido ou expirado.") from exc

    def _roles_from(self, claims: dict) -> list[str]:
        raw = claims.get(self.roles_claim) or []
        values = raw.replace(",", " ").split() if isinstance(raw, str) else [str(v) for v in raw]
        roles = [self.role_map.get(value, value) for value in values]
        return sorted({role for role in roles if role in ROLES})

    def _free_username(self, wanted: str, external_id: str) -> str:
        if self.users.find_by_username(wanted) is None:
            return wanted
        return f"{wanted}#{external_id[:12]}"

    def authenticate(self, token: str) -> User:
        claims = self._claims(token)
        external_id = str(claims["sub"])
        display_name = str(claims.get(self.name_claim) or "")
        user = self.users.find_by_external_id(external_id)

        if user is None:
            wanted = str(claims.get(self.username_claim) or external_id)
            user = User(
                user_id=str(uuid4()),
                username=self._free_username(wanted, external_id),
                display_name=display_name,
                roles=self._roles_from(claims) if self.roles_claim else list(self.default_roles),
                external_id=external_id,
                created_at=_now_iso(),
            )
            self.users.add_or_replace(user)
            logger.info("Utilizador externo criado: %s (%s)", user.username, ", ".join(user.roles) or "sem papéis")
        else:
            changes: dict = {}
            if self.roles_claim and (roles := self._roles_from(claims)) != user.roles:
                changes["roles"] = roles
            if display_name and display_name != user.display_name:
                changes["display_name"] = display_name
            if changes:
                user = user.model_copy(update=changes)
                self.users.add_or_replace(user)

        if not user.active:
            raise AuthError("Utilizador desativado.")
        return user


def build_authenticator(settings: Settings, users: UserRepository) -> Authenticator:
    if settings.auth_mode == "external":
        return ExternalAuthenticator(
            users,
            jwks_url=settings.auth_external_jwks_url,
            public_key=settings.auth_external_public_key,
            secret=settings.auth_external_secret,
            algorithms=settings.split_list(settings.auth_external_algorithms),
            issuer=settings.auth_external_issuer,
            audience=settings.auth_external_audience,
            username_claim=settings.auth_external_username_claim,
            name_claim=settings.auth_external_name_claim,
            roles_claim=settings.auth_external_roles_claim,
            role_map=json.loads(settings.auth_external_role_map or "{}"),
            default_roles=settings.split_list(settings.auth_external_default_roles),
        )
    if settings.auth_mode != "local":
        raise ValueError(f"AUTH_MODE desconhecido: {settings.auth_mode} (local ou external)")
    secret = settings.auth_secret_key
    if not secret:
        secret = secrets.token_urlsafe(32)
        logger.warning("AUTH_SECRET_KEY não definida: chave gerada no arranque, as sessões caem a cada reinício.")
    return LocalAuthenticator(users, secret, settings.auth_token_minutes)


def create_local_user(
    users: UserRepository, username: str, password: str, roles: list[str], display_name: str = ""
) -> User:
    user = User(
        user_id=str(uuid4()),
        username=username,
        display_name=display_name,
        roles=roles,
        created_at=_now_iso(),
    )
    users.add_or_replace(user)
    users.set_password_hash(user.user_id, hash_password(password))
    return user


def ensure_bootstrap_admin(settings: Settings, users: UserRepository) -> None:
    """Modo local sem utilizadores: cria o administrador de AUTH_BOOTSTRAP_ADMIN_* (ou avisa que falta)."""
    if settings.auth_mode != "local" or users.count() > 0:
        return
    username, password = settings.auth_bootstrap_admin_username, settings.auth_bootstrap_admin_password
    if not (username and password):
        logger.warning(
            "Não há utilizadores: define AUTH_BOOTSTRAP_ADMIN_USERNAME e AUTH_BOOTSTRAP_ADMIN_PASSWORD para criar o administrador."
        )
        return
    create_local_user(users, username, password, ["admin"], display_name="Administrador")
    logger.info("Administrador inicial criado: %s", username)
