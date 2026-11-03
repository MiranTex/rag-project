"""Dependências FastAPI de autenticação: current_user lê o token Bearer; require(permissão) protege um endpoint."""

from collections.abc import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.authenticators import AuthError
from backend.auth.permissions import AuthenticatedUser
from backend.dependencies import get_authenticator

_bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sessão em falta.", headers={"WWW-Authenticate": "Bearer"})
    try:
        user = get_authenticator().authenticate(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    return AuthenticatedUser.of(user)


def require(permission: str) -> Callable[..., AuthenticatedUser]:
    def dependency(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
        if not user.can(permission):
            raise HTTPException(status_code=403, detail="Sem permissão para esta operação.")
        return user

    return dependency
