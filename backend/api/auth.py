from fastapi import APIRouter, Depends, HTTPException

from backend.auth.authenticators import AuthError, LocalAuthenticator
from backend.auth.passwords import hash_password, verify_password
from backend.auth.permissions import AuthenticatedUser
from backend.api.security import current_user
from backend.config import get_settings
from backend.dependencies import get_authenticator, get_users
from backend.models import AuthConfig, CurrentUserInfo, LoginRequest, PasswordChange, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def user_info(user: AuthenticatedUser) -> CurrentUserInfo:
    return CurrentUserInfo(user=user.user, permissions=sorted(user.permissions))


def _local_authenticator() -> LocalAuthenticator:
    authenticator = get_authenticator()
    if not isinstance(authenticator, LocalAuthenticator):
        raise HTTPException(status_code=400, detail="O login é feito no sistema externo (AUTH_MODE=external).")
    return authenticator


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Público: o frontend decide se mostra o formulário de login ou espera um token do sistema externo."""
    return AuthConfig(mode=get_settings().auth_mode)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    authenticator = _local_authenticator()
    try:
        user = authenticator.login(payload.username.strip(), payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    token, expires_in = authenticator.issue(user)
    return TokenResponse(access_token=token, expires_in=expires_in, user=user_info(AuthenticatedUser.of(user)))


@router.get("/me", response_model=CurrentUserInfo)
def me(user: AuthenticatedUser = Depends(current_user)) -> CurrentUserInfo:
    return user_info(user)


@router.put("/password")
def change_password(payload: PasswordChange, user: AuthenticatedUser = Depends(current_user)) -> dict:
    _local_authenticator()
    users = get_users()
    if not verify_password(payload.current_password, users.password_hash(user.user_id)):
        raise HTTPException(status_code=400, detail="A palavra-passe atual não está correta.")
    users.set_password_hash(user.user_id, hash_password(payload.new_password))
    return {"message": "Palavra-passe alterada."}
