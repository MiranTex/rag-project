"""Permissões e papéis. Os endpoints verificam permissões, nunca papéis: um papel é só um conjunto de
permissões, por isso uma funcionalidade nova acrescenta uma permissão e decide-se aqui que papéis a têm."""

from dataclasses import dataclass

from backend.models import User

DOCUMENTS_READ = "documents:read"  # ver a lista de documentos e o texto extraído
DOCUMENTS_UPLOAD = "documents:upload"  # carregar, extrair de novo e remover
DOCUMENTS_REVIEW = "documents:review"  # corrigir o texto, a ficha e o nome antes de aprovar
DOCUMENTS_APPROVE = "documents:approve"  # aprovar para indexação
CHAT_USE = "chat:use"  # perguntar no chat e ao agente
CHAT_SELECT_DOCUMENT = "chat:select_document"  # restringir a pergunta a um documento (document_id)
USERS_MANAGE = "users:manage"  # criar utilizadores e atribuir papéis
SETTINGS_MANAGE = "settings:manage"  # alterar as configurações da aplicação

ALL_PERMISSIONS = frozenset(
    {
        DOCUMENTS_READ,
        DOCUMENTS_UPLOAD,
        DOCUMENTS_REVIEW,
        DOCUMENTS_APPROVE,
        CHAT_USE,
        CHAT_SELECT_DOCUMENT,
        USERS_MANAGE,
        SETTINGS_MANAGE,
    }
)

_DOCUMENT_CHAT = {DOCUMENTS_READ, CHAT_USE, CHAT_SELECT_DOCUMENT}

ROLES: dict[str, frozenset[str]] = {
    "admin": ALL_PERMISSIONS,
    "manager": frozenset(_DOCUMENT_CHAT | {DOCUMENTS_UPLOAD, DOCUMENTS_REVIEW, DOCUMENTS_APPROVE}),
    # Para separar quem carrega de quem aprova (ver REQUIRE_SEPARATE_APPROVER).
    "uploader": frozenset(_DOCUMENT_CHAT | {DOCUMENTS_UPLOAD, DOCUMENTS_REVIEW}),
    "reviewer": frozenset(_DOCUMENT_CHAT | {DOCUMENTS_REVIEW, DOCUMENTS_APPROVE}),
    # Só o chat: não vê a lista de documentos nem escolhe um documento (pode pedi-lo por texto ao agente).
    "chat": frozenset({CHAT_USE}),
}


def unknown_roles(roles: list[str]) -> list[str]:
    return [role for role in roles if role not in ROLES]


def permissions_for(roles: list[str]) -> frozenset[str]:
    return frozenset().union(*(ROLES.get(role, frozenset()) for role in roles))


@dataclass(frozen=True)
class AuthenticatedUser:
    """Utilizador do pedido atual, com as permissões já calculadas."""

    user: User
    permissions: frozenset[str]

    @classmethod
    def of(cls, user: User) -> "AuthenticatedUser":
        return cls(user=user, permissions=permissions_for(user.roles))

    @property
    def user_id(self) -> str:
        return self.user.user_id

    def can(self, permission: str) -> bool:
        return permission in self.permissions
