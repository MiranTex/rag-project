"""Página pública de um convite para um projeto: ver o convite, aceitá-lo com a conta atual ou criar conta.

Quem tem o link pode entrar no projeto (é o que um convite significa): o token tem 256 bits, só o hash fica
guardado, serve uma vez e expira (INVITE_VALID_DAYS). Criar conta pelo convite só existe no login local e pode
ser desligado (INVITE_SIGNUP_ENABLED); a conta nova recebe os papéis de INVITE_SIGNUP_ROLES."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import user_info
from backend.api.research_projects import invitation_status, token_hash
from backend.api.security import current_user
from backend.auth.authenticators import LocalAuthenticator, create_local_user
from backend.auth.permissions import AuthenticatedUser, unknown_roles
from backend.config import get_settings
from backend.dependencies import get_authenticator, get_research_repository, get_users
from backend.models import TokenResponse
from backend.research.models import InvitationInfo, InvitationSignup, ProjectInvitation, ProjectMember

router = APIRouter(prefix="/invitations", tags=["research"])

_ROLE_LEVEL = {"viewer": 0, "editor": 1}


def _signup_roles() -> list[str]:
    roles = [r.strip() for r in get_settings().invite_signup_roles.split(",") if r.strip()]
    if not roles or unknown_roles(roles):
        raise HTTPException(status_code=500, detail="INVITE_SIGNUP_ROLES tem papéis desconhecidos.")
    return roles


def _signup_allowed() -> bool:
    settings = get_settings()
    return settings.auth_mode == "local" and settings.invite_signup_enabled


def _pending(token: str) -> ProjectInvitation:
    invitation = get_research_repository().get_invitation_by_token_hash(token_hash(token))
    if invitation is None:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    status = invitation_status(invitation)
    if status != "pending":
        raise HTTPException(status_code=410, detail="Este convite já foi usado." if status == "accepted" else "Este convite expirou.")
    return invitation


def _join(invitation: ProjectInvitation, user_id: str) -> str:
    """Junta a pessoa ao projeto (sem baixar o papel de quem já é membro) e gasta o convite."""
    repo = get_research_repository()
    project = repo.get_project(invitation.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="O projeto já não existe.")
    if project.owner_id != user_id:
        current = next((m.role for m in repo.list_members(project.project_id) if m.user_id == user_id), None)
        if current is None or _ROLE_LEVEL[invitation.role] > _ROLE_LEVEL[current]:
            repo.set_member(ProjectMember(project_id=project.project_id, user_id=user_id, role=invitation.role))
    repo.save_invitation(invitation.model_copy(update={"accepted_by": user_id, "accepted_at": datetime.now(UTC).isoformat()}))
    return project.project_id


@router.get("/{token}", response_model=InvitationInfo)
def invitation_info(token: str) -> InvitationInfo:
    """Público: mostra o convite sem pedir login (para decidir entre entrar e criar conta)."""
    invitation = get_research_repository().get_invitation_by_token_hash(token_hash(token))
    project = get_research_repository().get_project(invitation.project_id) if invitation else None
    if invitation is None or project is None:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    inviter = get_users().find_by_id(invitation.invited_by)
    return InvitationInfo(
        project_title=project.title,
        invited_by=(inviter.display_name or inviter.username) if inviter else "",
        email=invitation.email,
        role=invitation.role,
        status=invitation_status(invitation),
        signup_allowed=_signup_allowed(),
    )


@router.post("/{token}/accept")
def accept_invitation(token: str, user: AuthenticatedUser = Depends(current_user)) -> dict:
    return {"project_id": _join(_pending(token), user.user_id)}


@router.post("/{token}/signup", response_model=TokenResponse)
def signup_with_invitation(token: str, payload: InvitationSignup) -> TokenResponse:
    if not _signup_allowed():
        raise HTTPException(status_code=403, detail="Não é possível criar conta por convite; pede uma conta a quem gere a aplicação.")
    invitation = _pending(token)
    users = get_users()
    username = payload.username.strip()
    if users.find_by_username(username):
        raise HTTPException(status_code=409, detail="Já existe um utilizador com esse nome. Se é teu, entra e aceita o convite.")
    user = create_local_user(users, username, payload.password, _signup_roles(), payload.display_name.strip())
    _join(invitation, user.user_id)
    authenticator = get_authenticator()
    if not isinstance(authenticator, LocalAuthenticator):
        raise HTTPException(status_code=400, detail="O login é feito no sistema externo.")
    access_token, expires_in = authenticator.issue(user)
    return TokenResponse(access_token=access_token, expires_in=expires_in, user=user_info(AuthenticatedUser.of(user)))
