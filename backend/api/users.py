from fastapi import APIRouter, Depends, HTTPException

from backend.auth.authenticators import create_local_user
from backend.auth.passwords import hash_password
from backend.auth.permissions import ROLES, USERS_MANAGE, AuthenticatedUser, permissions_for, unknown_roles
from backend.api.security import require
from backend.config import get_settings
from backend.dependencies import get_users
from backend.models import User, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

manage_users = require(USERS_MANAGE)


def _check_roles(roles: list[str]) -> None:
    if unknown := unknown_roles(roles):
        raise HTTPException(status_code=422, detail=f"Papéis desconhecidos: {', '.join(unknown)}")


@router.get("/roles")
def list_roles(_: AuthenticatedUser = Depends(manage_users)) -> dict[str, list[str]]:
    return {role: sorted(permissions) for role, permissions in ROLES.items()}


@router.get("", response_model=list[User])
def list_users(_: AuthenticatedUser = Depends(manage_users)) -> list[User]:
    return get_users().list_users()


@router.post("", response_model=User)
def create_user(payload: UserCreate, _: AuthenticatedUser = Depends(manage_users)) -> User:
    """Só no modo local; no modo externo os utilizadores são criados no primeiro acesso."""
    if get_settings().auth_mode != "local":
        raise HTTPException(status_code=400, detail="Com login externo, os utilizadores são criados no primeiro acesso.")
    _check_roles(payload.roles)
    username = payload.username.strip()
    users = get_users()
    if users.find_by_username(username):
        raise HTTPException(status_code=409, detail="Já existe um utilizador com esse nome.")
    return create_local_user(users, username, payload.password, payload.roles, payload.display_name.strip())


@router.patch("/{user_id}", response_model=User)
def update_user(user_id: str, payload: UserUpdate, admin: AuthenticatedUser = Depends(manage_users)) -> User:
    settings = get_settings()
    users = get_users()
    user = users.find_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado.")

    changes: dict = {}
    if payload.display_name is not None:
        changes["display_name"] = payload.display_name.strip()
    if payload.roles is not None:
        if settings.auth_mode == "external" and settings.auth_external_roles_claim:
            raise HTTPException(status_code=400, detail="Os papéis vêm do sistema externo (AUTH_EXTERNAL_ROLES_CLAIM).")
        _check_roles(payload.roles)
        changes["roles"] = sorted(set(payload.roles))
    if payload.active is not None:
        changes["active"] = payload.active
    if payload.password is not None and (settings.auth_mode != "local" or user.external_id):
        raise HTTPException(status_code=400, detail="A palavra-passe de um utilizador externo é gerida no sistema externo.")

    updated = user.model_copy(update=changes)
    # Ninguém se tranca fora: o administrador não se desativa nem perde a gestão de utilizadores.
    if user_id == admin.user_id and not (updated.active and USERS_MANAGE in permissions_for(updated.roles)):
        raise HTTPException(status_code=400, detail="Não podes desativar-te nem retirar-te a gestão de utilizadores.")

    users.add_or_replace(updated)
    if payload.password is not None:
        users.set_password_hash(user_id, hash_password(payload.password))
    return updated
