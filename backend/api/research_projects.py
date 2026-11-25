"""Projetos de pesquisa: documentos fixados, caderno (notas, destaques, respostas guardadas), comentários,
partilha com outras pessoas, matriz de literatura, bibliografia e rascunho do estado da arte."""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.agent.tools.base import ToolError
from backend.api.security import require
from backend.auth.permissions import RESEARCH_USE, AuthenticatedUser
from backend.config import get_settings
from backend.dependencies import (
    get_document_types,
    get_extraction_store,
    get_llm_credentials,
    get_registry,
    get_research_repository,
    get_users,
    llm_for,
)
from backend.research.access import load_project, project_document_ids, research_context
from backend.research.bibliography import bibliography
from backend.research.conversation import draft_project
from backend.research.library import indexed_cards, indexed_document
from backend.research.models import (
    CitationStyle,
    Comment,
    CommentCreate,
    CommentView,
    ConversationDraftRequest,
    ConversationSave,
    ConversationSummary,
    ConversationView,
    InvitationCreate,
    InvitationCreated,
    InvitationView,
    ItemCreate,
    ItemUpdate,
    ItemView,
    MatrixFillRequest,
    MatrixUpdate,
    MemberAdd,
    MemberInfo,
    NotebookItem,
    Project,
    ProjectCreate,
    ProjectDetail,
    ProjectConversation,
    ProjectDocument,
    ProjectDraft,
    ProjectInvitation,
    ProjectFromDraft,
    ProjectFromDraftResult,
    ProjectMember,
    ProjectStructure,
    ProjectSummary,
    ProjectUpdate,
    StateOfArtRequest,
)
from backend.research.writing import fill_matrix, state_of_art

router = APIRouter(prefix="/research/projects", tags=["research"])

can_research = require(RESEARCH_USE)
MAX_MATRIX_DOCUMENTS = 8


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _names() -> dict[str, str]:
    """Nome a mostrar de cada utilizador (para autores de notas e comentários)."""
    return {u.user_id: u.display_name or u.username for u in get_users().list_users()}


def _detail(project: Project, role: str) -> ProjectDetail:
    users = {u.user_id: u for u in get_users().list_users()}
    members = []
    owner = users.get(project.owner_id)
    if owner:
        members.append(MemberInfo(user_id=owner.user_id, username=owner.username, display_name=owner.display_name, role="owner"))
    for member in get_research_repository().list_members(project.project_id):
        if user := users.get(member.user_id):
            members.append(MemberInfo(user_id=user.user_id, username=user.username, display_name=user.display_name, role=member.role))
    pinned = [d.document_id for d in get_research_repository().list_project_documents(project.project_id)]
    return ProjectDetail(
        project=project,
        my_role=role,
        members=members,
        documents=indexed_cards(get_registry(), get_extraction_store(), pinned),
    )


def _touch(project: Project) -> None:
    get_research_repository().save_project(project.model_copy(update={"updated_at": _now()}))


def _clean_tags(tags: list[str]) -> list[str]:
    return sorted({" ".join(tag.split()).lower() for tag in tags if tag.strip()})


def _clean_structure(structure: ProjectStructure) -> ProjectStructure:
    """Secções com chaves únicas e estados sem repetidos (a ordem é a que a pessoa escolheu)."""
    sections, keys = [], set()
    for section in structure.sections:
        key = section.key.strip()
        if key in keys:
            raise HTTPException(status_code=422, detail=f"Secção repetida: {key}")
        keys.add(key)
        sections.append(section.model_copy(update={"key": key, "title": section.title.strip(), "description": section.description.strip()}))
    statuses = list(dict.fromkeys(" ".join(s.split()).lower() for s in structure.statuses if s.strip()))
    return ProjectStructure(sections=sections, statuses=statuses)


def _check_item_fields(project: Project, section: str | None, status: str | None) -> None:
    """A secção e o estado de uma entrada têm de existir na estrutura do projeto (vazio é sempre válido)."""
    if section and section not in {s.key for s in project.structure.sections}:
        raise HTTPException(status_code=422, detail=f"Secção desconhecida neste projeto: {section}")
    if status and status not in project.structure.statuses:
        raise HTTPException(status_code=422, detail=f"Estado desconhecido neste projeto: {status}")


@router.get("", response_model=list[ProjectSummary])
def list_projects(user: AuthenticatedUser = Depends(can_research)) -> list[ProjectSummary]:
    repo = get_research_repository()
    summaries = []
    for project in repo.list_projects_for(user.user_id):
        role = "owner" if project.owner_id == user.user_id else next(
            (m.role for m in repo.list_members(project.project_id) if m.user_id == user.user_id), "viewer"
        )
        summaries.append(
            ProjectSummary(
                project=project,
                my_role=role,
                document_count=len(project_document_ids(project.project_id)),
                item_count=repo.count_items(project.project_id),
            )
        )
    return summaries


@router.post("", response_model=ProjectDetail)
def create_project(payload: ProjectCreate, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail:
    if payload.work_type and payload.work_type not in get_document_types().types:
        raise HTTPException(status_code=422, detail=f"Tipo de trabalho desconhecido: {payload.work_type}")
    now = _now()
    project = Project(
        project_id=str(uuid4()),
        owner_id=user.user_id,
        title=payload.title.strip(),
        question=payload.question.strip(),
        description=payload.description.strip(),
        work_type=payload.work_type,
        structure=_clean_structure(payload.structure),
        created_at=now,
        updated_at=now,
    )
    get_research_repository().save_project(project)
    return _detail(project, "owner")


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail:
    project, role = load_project(project_id, user)
    return _detail(project, role)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(project_id: str, payload: ProjectUpdate, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail:
    project, role = load_project(project_id, user, "editor")
    changes = {key: value.strip() for key, value in payload.model_dump(exclude_none=True, exclude={"structure"}).items()}
    if changes.get("work_type") and changes["work_type"] not in get_document_types().types:
        raise HTTPException(status_code=422, detail=f"Tipo de trabalho desconhecido: {changes['work_type']}")
    if payload.structure is not None:
        changes["structure"] = _clean_structure(payload.structure)
    project = project.model_copy(update={**changes, "updated_at": _now()})
    get_research_repository().save_project(project)
    return _detail(project, role)


@router.delete("/{project_id}")
def delete_project(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "owner")
    get_research_repository().delete_project(project_id)
    get_llm_credentials().delete("project", project_id)
    return {"message": "Projeto apagado."}


# ---- Projeto a partir de uma conversa do chat ----


@router.post("/draft-from-conversation", response_model=ProjectDraft)
async def draft_from_conversation(payload: ConversationDraftRequest, user: AuthenticatedUser = Depends(can_research)) -> ProjectDraft:
    """Propõe um projeto (estrutura e entradas) a partir da conversa; não grava nada."""

    def run() -> ProjectDraft:
        try:
            # Ainda não há projeto: paga a pessoa (se tem chave) ou a plataforma.
            draft = draft_project(payload.turns, payload.goal, llm_for(user.user_id, None, "utility"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        registry = get_registry()
        return draft.model_copy(update={"document_ids": [d for d in draft.document_ids if indexed_document(registry, d)]})

    return await run_in_threadpool(run)


@router.post("/from-draft", response_model=ProjectFromDraftResult)
def create_from_draft(payload: ProjectFromDraft, user: AuthenticatedUser = Depends(can_research)) -> ProjectFromDraftResult:
    """Cria o projeto revisto pela pessoa: documentos fixados, entradas, a conversa guardada e os membros."""
    repo, registry, warnings = get_research_repository(), get_registry(), []
    now = _now()
    project = Project(
        project_id=str(uuid4()),
        owner_id=user.user_id,
        title=payload.title.strip(),
        question=payload.question.strip(),
        description=payload.description.strip(),
        structure=_clean_structure(payload.structure),
        created_at=now,
        updated_at=now,
    )
    for draft in payload.items:
        _check_item_fields(project, draft.section, draft.status)
    repo.save_project(project)

    for document_id in dict.fromkeys(payload.document_ids):
        if indexed_document(registry, document_id) is None:
            warnings.append(f"Documento {document_id} não está indexado; não foi fixado.")
            continue
        repo.add_project_document(ProjectDocument(project_id=project.project_id, document_id=document_id, added_by=user.user_id, added_at=now))

    # Cada entrada recebe um instante um pouco diferente, para a ordem da proposta se manter no caderno.
    start = datetime.now(UTC)

    def stamp(n: int) -> str:
        return (start + timedelta(microseconds=n)).isoformat()

    n = 0
    for turn in payload.conversation:
        if not turn.answer.strip():
            continue
        n += 1
        repo.save_item(
            NotebookItem(
                item_id=str(uuid4()),
                project_id=project.project_id,
                kind="answer",
                title=turn.question.strip()[:300],
                text=turn.answer.strip(),
                source={
                    "question": turn.question.strip(),
                    "sources": [s.model_dump(exclude={"text"}) for s in turn.sources if s.document_id],
                    "origin": "conversation",
                },
                created_by=user.user_id,
                created_at=stamp(n),
                updated_at=stamp(n),
            )
        )
    for draft in payload.items:
        if not (draft.title.strip() or draft.text.strip()):
            continue
        n += 1
        repo.save_item(
            NotebookItem(
                item_id=str(uuid4()),
                project_id=project.project_id,
                kind="note",
                title=draft.title.strip(),
                text=draft.text.strip(),
                source={"sources": draft.sources, "origin": "conversation"} if draft.sources else {"origin": "conversation"},
                section=draft.section,
                ref=draft.ref.strip(),
                status=draft.status,
                fields=draft.fields,
                created_by=user.user_id,
                created_at=stamp(n),
                updated_at=stamp(n),
            )
        )

    users = get_users()
    for member in payload.members:
        found = users.find_by_username(member.username.strip())
        if found is None or not found.active:
            warnings.append(f"Utilizador não encontrado: {member.username}")
        elif found.user_id != user.user_id:
            repo.set_member(ProjectMember(project_id=project.project_id, user_id=found.user_id, role=member.role))

    return ProjectFromDraftResult(detail=_detail(project, "owner"), warnings=warnings)


# ---- Partilha ----


@router.post("/{project_id}/members", response_model=ProjectDetail)
def add_member(project_id: str, payload: MemberAdd, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail:
    project, role = load_project(project_id, user, "owner")
    member = get_users().find_by_username(payload.username.strip())
    if member is None or not member.active:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado.")
    if member.user_id == project.owner_id:
        raise HTTPException(status_code=400, detail="O dono já tem acesso ao projeto.")
    get_research_repository().set_member(ProjectMember(project_id=project_id, user_id=member.user_id, role=payload.role))
    return _detail(project, role)


@router.delete("/{project_id}/members/{user_id}", response_model=ProjectDetail | None)
def remove_member(project_id: str, user_id: str, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail | None:
    """O dono remove qualquer membro; um membro pode sair do projeto."""
    project, role = load_project(project_id, user)
    if role != "owner" and user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Só o dono gere os membros do projeto.")
    get_research_repository().remove_member(project_id, user_id)
    return _detail(project, role) if role == "owner" else None


# ---- Convites por email (para quem ainda não tem conta) ----


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def invitation_status(invitation: ProjectInvitation) -> str:
    if invitation.accepted_at:
        return "accepted"
    return "expired" if invitation.expires_at < _now() else "pending"


def _invitation_view(invitation: ProjectInvitation, names: dict[str, str]) -> InvitationView:
    return InvitationView(**invitation.model_dump(exclude={"invited_by"}), invited_by=names.get(invitation.invited_by, ""))


@router.post("/{project_id}/invitations", response_model=InvitationCreated)
def create_invitation(project_id: str, payload: InvitationCreate, user: AuthenticatedUser = Depends(can_research)) -> InvitationCreated:
    """O link (com o token) só aparece nesta resposta; guarda-se o hash. Não há envio de email: quem convida
    copia o link e envia-o pelo meio que preferir."""
    load_project(project_id, user, "owner")
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    invitation = ProjectInvitation(
        invitation_id=str(uuid4()),
        project_id=project_id,
        email=payload.email.strip().lower(),
        role=payload.role,
        token_hash=token_hash(token),
        invited_by=user.user_id,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(days=get_settings().invite_valid_days)).isoformat(),
    )
    get_research_repository().save_invitation(invitation)
    return InvitationCreated(**_invitation_view(invitation, _names()).model_dump(), token=token)


@router.get("/{project_id}/invitations", response_model=list[InvitationView])
def list_invitations(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> list[InvitationView]:
    """Convites por aceitar e ainda válidos."""
    load_project(project_id, user, "owner")
    names = _names()
    return [
        _invitation_view(i, names)
        for i in get_research_repository().list_invitations(project_id)
        if invitation_status(i) == "pending"
    ]


@router.delete("/{project_id}/invitations/{invitation_id}")
def revoke_invitation(project_id: str, invitation_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "owner")
    repo = get_research_repository()
    if not any(i.invitation_id == invitation_id for i in repo.list_invitations(project_id)):
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    repo.delete_invitation(invitation_id)
    return {"message": "Convite anulado."}


# ---- Documentos fixados ----


@router.post("/{project_id}/documents/{document_id}", response_model=ProjectDetail)
def pin_document(project_id: str, document_id: str, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail:
    project, role = load_project(project_id, user, "editor")
    if indexed_document(get_registry(), document_id) is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    get_research_repository().add_project_document(
        ProjectDocument(project_id=project_id, document_id=document_id, added_by=user.user_id, added_at=_now())
    )
    _touch(project)
    return _detail(project, role)


@router.delete("/{project_id}/documents/{document_id}", response_model=ProjectDetail)
def unpin_document(project_id: str, document_id: str, user: AuthenticatedUser = Depends(can_research)) -> ProjectDetail:
    project, role = load_project(project_id, user, "editor")
    get_research_repository().remove_project_document(project_id, document_id)
    _touch(project)
    return _detail(project, role)


# ---- Caderno ----


def _item_view(item: NotebookItem, names: dict[str, str], comment_counts: dict[str, int]) -> ItemView:
    return ItemView(**item.model_dump(), author=names.get(item.created_by, ""), comment_count=comment_counts.get(item.item_id, 0))


@router.get("/{project_id}/items", response_model=list[ItemView])
def list_items(
    project_id: str,
    kind: str | None = None,
    q: str | None = None,
    tag: str | None = None,
    section: str | None = None,
    user: AuthenticatedUser = Depends(can_research),
) -> list[ItemView]:
    load_project(project_id, user)
    repo = get_research_repository()
    items = repo.list_items(project_id, kind=kind, query=q.strip() if q else None)
    if tag:
        items = [item for item in items if tag.lower() in item.tags]
    if section is not None:
        items = [item for item in items if item.section == section]
    counts: dict[str, int] = {}
    for comment in repo.list_comments(project_id):
        if comment.item_id:
            counts[comment.item_id] = counts.get(comment.item_id, 0) + 1
    names = _names()
    return [_item_view(item, names, counts) for item in items]


@router.post("/{project_id}/items", response_model=ItemView)
def create_item(project_id: str, payload: ItemCreate, user: AuthenticatedUser = Depends(can_research)) -> ItemView:
    project, _ = load_project(project_id, user, "editor")
    if not (payload.text.strip() or payload.title.strip()):
        raise HTTPException(status_code=422, detail="A entrada precisa de título ou texto.")
    _check_item_fields(project, payload.section, payload.status)
    now = _now()
    item = NotebookItem(
        item_id=str(uuid4()),
        project_id=project_id,
        kind=payload.kind,
        title=payload.title.strip(),
        text=payload.text.strip(),
        source=payload.source,
        tags=_clean_tags(payload.tags),
        section=payload.section,
        ref=payload.ref.strip(),
        status=payload.status,
        fields=payload.fields,
        created_by=user.user_id,
        created_at=now,
        updated_at=now,
    )
    get_research_repository().save_item(item)
    _touch(project)
    return _item_view(item, _names(), {})


def _project_item(project_id: str, item_id: str) -> NotebookItem:
    item = get_research_repository().get_item(item_id)
    if item is None or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Entrada não encontrada.")
    return item


@router.patch("/{project_id}/items/{item_id}", response_model=ItemView)
def update_item(project_id: str, item_id: str, payload: ItemUpdate, user: AuthenticatedUser = Depends(can_research)) -> ItemView:
    project, _ = load_project(project_id, user, "editor")
    item = _project_item(project_id, item_id)
    changes = payload.model_dump(exclude_none=True)
    source_updates = {key: changes.pop(key) for key in ("basis", "via") if key in changes}
    if source_updates:
        changes["source"] = {**item.source, **source_updates}
    _check_item_fields(project, changes.get("section"), changes.get("status"))
    if "tags" in changes:
        changes["tags"] = _clean_tags(changes["tags"])
    for key in ("title", "text", "ref"):
        if key in changes:
            changes[key] = changes[key].strip()
    item = item.model_copy(update={**changes, "updated_at": _now()})
    get_research_repository().save_item(item)
    _touch(project)
    return _item_view(item, _names(), {})


@router.delete("/{project_id}/items/{item_id}")
def delete_item(project_id: str, item_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "editor")
    _project_item(project_id, item_id)
    get_research_repository().delete_item(item_id)
    return {"message": "Entrada apagada."}


# ---- Conversas do chat guardadas no projeto ----

MAX_CONVERSATION_BYTES = 2_000_000


def _conversation_summary(conversation: ProjectConversation, names: dict[str, str]) -> dict:
    return {
        **conversation.model_dump(exclude={"messages"}),
        "author": names.get(conversation.created_by, ""),
        "message_count": len(conversation.messages),
        "pending_proposals": sum(
            1 for m in conversation.messages for p in (m.get("proposals") or []) if isinstance(p, dict) and not p.get("decision")
        ),
    }


def _can_write_conversation(conversation: ProjectConversation, user: AuthenticatedUser, role: str) -> bool:
    """Quem a começou continua-a; quem edita o projeto também (para aceitar propostas ou continuar o trabalho)."""
    return conversation.created_by == user.user_id or role != "viewer"


def _conversation_view(conversation: ProjectConversation, user: AuthenticatedUser, role: str) -> ConversationView:
    return ConversationView(
        **_conversation_summary(conversation, _names()),
        messages=conversation.messages,
        can_edit=_can_write_conversation(conversation, user, role),
    )


def _clean_messages(messages: list[dict]) -> list[dict]:
    if len(json.dumps(messages, ensure_ascii=False, default=str)) > MAX_CONVERSATION_BYTES:
        raise HTTPException(status_code=413, detail="A conversa é demasiado grande para guardar; começa uma nova.")
    return messages


def _conversation_title(title: str, messages: list[dict]) -> str:
    first = next((str(m.get("question", "")).strip() for m in messages if str(m.get("question", "")).strip()), "")
    return (title.strip() or first or "Conversa")[:200]


def _project_conversation(project_id: str, conversation_id: str) -> ProjectConversation:
    conversation = get_research_repository().get_conversation(conversation_id)
    if conversation is None or conversation.project_id != project_id:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return conversation


@router.get("/{project_id}/conversations", response_model=list[ConversationSummary])
def list_conversations(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> list[ConversationSummary]:
    load_project(project_id, user)
    names = _names()
    return [ConversationSummary(**_conversation_summary(c, names)) for c in get_research_repository().list_conversations(project_id)]


@router.post("/{project_id}/conversations", response_model=ConversationView)
def create_conversation(project_id: str, payload: ConversationSave, user: AuthenticatedUser = Depends(can_research)) -> ConversationView:
    """Qualquer membro pode conversar no projeto (quem só lê também pergunta; não aplica propostas)."""
    _, role = load_project(project_id, user)
    now = _now()
    messages = _clean_messages(payload.messages)
    conversation = ProjectConversation(
        conversation_id=str(uuid4()),
        project_id=project_id,
        title=_conversation_title(payload.title, messages),
        created_by=user.user_id,
        messages=messages,
        created_at=now,
        updated_at=now,
    )
    get_research_repository().save_conversation(conversation)
    return _conversation_view(conversation, user, role)


@router.get("/{project_id}/conversations/{conversation_id}", response_model=ConversationView)
def get_conversation(project_id: str, conversation_id: str, user: AuthenticatedUser = Depends(can_research)) -> ConversationView:
    _, role = load_project(project_id, user)
    return _conversation_view(_project_conversation(project_id, conversation_id), user, role)


@router.put("/{project_id}/conversations/{conversation_id}", response_model=ConversationView)
def save_conversation(
    project_id: str, conversation_id: str, payload: ConversationSave, user: AuthenticatedUser = Depends(can_research)
) -> ConversationView:
    _, role = load_project(project_id, user)
    conversation = _project_conversation(project_id, conversation_id)
    if not _can_write_conversation(conversation, user, role):
        raise HTTPException(status_code=403, detail="Só quem começou a conversa (ou quem edita o projeto) a pode continuar.")
    messages = _clean_messages(payload.messages)
    conversation = conversation.model_copy(
        update={"messages": messages, "title": payload.title.strip()[:200] or conversation.title, "updated_at": _now()}
    )
    get_research_repository().save_conversation(conversation)
    return _conversation_view(conversation, user, role)


@router.delete("/{project_id}/conversations/{conversation_id}")
def delete_conversation(project_id: str, conversation_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    _, role = load_project(project_id, user)
    conversation = _project_conversation(project_id, conversation_id)
    if conversation.created_by != user.user_id and role != "owner":
        raise HTTPException(status_code=403, detail="Só quem começou a conversa (ou o dono do projeto) a pode apagar.")
    get_research_repository().delete_conversation(conversation_id)
    return {"message": "Conversa apagada."}


# ---- Comentários (qualquer membro, incluindo quem só lê) ----


@router.get("/{project_id}/comments", response_model=list[CommentView])
def list_comments(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> list[CommentView]:
    load_project(project_id, user)
    names = _names()
    return [CommentView(**c.model_dump(), author=names.get(c.author_id, "")) for c in get_research_repository().list_comments(project_id)]


@router.post("/{project_id}/comments", response_model=CommentView)
def add_comment(project_id: str, payload: CommentCreate, user: AuthenticatedUser = Depends(can_research)) -> CommentView:
    load_project(project_id, user)
    if payload.item_id:
        _project_item(project_id, payload.item_id)
    comment = Comment(
        comment_id=str(uuid4()),
        project_id=project_id,
        item_id=payload.item_id,
        author_id=user.user_id,
        text=payload.text.strip(),
        created_at=_now(),
    )
    get_research_repository().add_comment(comment)
    return CommentView(**comment.model_dump(), author=user.user.display_name or user.user.username)


@router.delete("/{project_id}/comments/{comment_id}")
def delete_comment(project_id: str, comment_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    _, role = load_project(project_id, user)
    comment = get_research_repository().get_comment(comment_id)
    if comment is None or comment.project_id != project_id:
        raise HTTPException(status_code=404, detail="Comentário não encontrado.")
    if comment.author_id != user.user_id and role != "owner":
        raise HTTPException(status_code=403, detail="Só quem escreveu o comentário (ou o dono do projeto) o pode apagar.")
    get_research_repository().delete_comment(comment_id)
    return {"message": "Comentário apagado."}


# ---- Matriz de literatura ----


def _matrix_view(project_id: str, data: dict | None) -> dict:
    """Matriz com as linhas = documentos fixados (os acrescentados depois de preencher aparecem vazios)."""
    data = data or {"dimensions": [], "cells": {}, "notes": {}}
    cards = indexed_cards(get_registry(), get_extraction_store(), project_document_ids(project_id))
    return {
        "dimensions": data.get("dimensions", []),
        "documents": [card.model_dump() for card in cards],
        "cells": data.get("cells", {}),
        "notes": data.get("notes", {}),
    }


@router.get("/{project_id}/matrix")
def get_matrix(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user)
    return _matrix_view(project_id, get_research_repository().get_matrix(project_id))


@router.put("/{project_id}/matrix")
def update_matrix(project_id: str, payload: MatrixUpdate, user: AuthenticatedUser = Depends(can_research)) -> dict:
    """Guarda as dimensões e as notas escritas pela pessoa em cada célula (os excertos ficam)."""
    load_project(project_id, user, "editor")
    repo = get_research_repository()
    data = repo.get_matrix(project_id) or {"cells": {}}
    data.update(dimensions=[d.strip() for d in payload.dimensions if d.strip()], notes=payload.notes)
    repo.save_matrix(project_id, data, _now())
    return _matrix_view(project_id, data)


@router.post("/{project_id}/matrix/fill")
async def fill_project_matrix(project_id: str, payload: MatrixFillRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    """Preenche as células com excertos de cada documento fixado e um resumo curto (mantém as notas)."""
    load_project(project_id, user, "editor")
    ids = project_document_ids(project_id)
    if not 2 <= len(ids) <= MAX_MATRIX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"A matriz precisa de 2 a {MAX_MATRIX_DOCUMENTS} documentos fixados no projeto.")
    dimensions = [d.strip() for d in payload.dimensions if d.strip()]
    cards = indexed_cards(get_registry(), get_extraction_store(), ids)

    def run() -> dict:
        try:
            filled = fill_matrix(cards, dimensions, research_context(user, ids), llm_for(user.user_id, project_id, "utility"))
        except ToolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repo = get_research_repository()
        data = repo.get_matrix(project_id) or {}
        data.update(filled)
        data.setdefault("notes", {})
        repo.save_matrix(project_id, data, _now())
        return _matrix_view(project_id, data)

    return await run_in_threadpool(run)


# ---- Bibliografia e estado da arte ----


@router.get("/{project_id}/bibliography")
def project_bibliography(project_id: str, style: CitationStyle = "apa", user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user)
    cards = indexed_cards(get_registry(), get_extraction_store(), project_document_ids(project_id))
    return {"style": style, "references": bibliography(cards, style)}


@router.post("/{project_id}/state-of-the-art")
async def project_state_of_art(project_id: str, payload: StateOfArtRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    project, _ = load_project(project_id, user)
    ids = project_document_ids(project_id)
    if not ids:
        raise HTTPException(status_code=400, detail="Fixa documentos no projeto antes de pedir o estado da arte.")
    topic = payload.topic.strip() or project.question or project.title
    cards = indexed_cards(get_registry(), get_extraction_store(), ids)[: payload.max_documents]

    def run() -> dict:
        try:
            result = state_of_art(topic, cards, research_context(user, ids), llm_for(user.user_id, project_id))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Não foi possível gerar o rascunho: {exc}") from exc
        result["bibliography"] = bibliography(cards, "apa")
        return result

    return await run_in_threadpool(run)
