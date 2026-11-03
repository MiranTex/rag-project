"""Projetos de pesquisa: documentos fixados, caderno (notas, destaques, respostas guardadas), comentários,
partilha com outras pessoas, matriz de literatura, bibliografia e rascunho do estado da arte."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.agent.tools.base import ToolError
from backend.api.security import require
from backend.auth.permissions import RESEARCH_USE, AuthenticatedUser
from backend.dependencies import (
    get_document_types,
    get_extraction_store,
    get_lmstudio_client,
    get_registry,
    get_research_repository,
    get_users,
    get_utility_llm,
)
from backend.research.access import load_project, project_document_ids, research_context
from backend.research.bibliography import bibliography
from backend.research.library import indexed_cards, indexed_document
from backend.research.models import (
    CitationStyle,
    Comment,
    CommentCreate,
    CommentView,
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
    ProjectDocument,
    ProjectMember,
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
    changes = {key: value.strip() for key, value in payload.model_dump(exclude_none=True).items()}
    if changes.get("work_type") and changes["work_type"] not in get_document_types().types:
        raise HTTPException(status_code=422, detail=f"Tipo de trabalho desconhecido: {changes['work_type']}")
    project = project.model_copy(update={**changes, "updated_at": _now()})
    get_research_repository().save_project(project)
    return _detail(project, role)


@router.delete("/{project_id}")
def delete_project(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "owner")
    get_research_repository().delete_project(project_id)
    return {"message": "Projeto apagado."}


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
    user: AuthenticatedUser = Depends(can_research),
) -> list[ItemView]:
    load_project(project_id, user)
    repo = get_research_repository()
    items = repo.list_items(project_id, kind=kind, query=q.strip() if q else None)
    if tag:
        items = [item for item in items if tag.lower() in item.tags]
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
    now = _now()
    item = NotebookItem(
        item_id=str(uuid4()),
        project_id=project_id,
        kind=payload.kind,
        title=payload.title.strip(),
        text=payload.text.strip(),
        source=payload.source,
        tags=_clean_tags(payload.tags),
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
    if "tags" in changes:
        changes["tags"] = _clean_tags(changes["tags"])
    for key in ("title", "text"):
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
            filled = fill_matrix(cards, dimensions, research_context(user, ids), get_utility_llm())
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
            result = state_of_art(topic, cards, research_context(user, ids), get_lmstudio_client())
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Não foi possível gerar o rascunho: {exc}") from exc
        result["bibliography"] = bibliography(cards, "apa")
        return result

    return await run_in_threadpool(run)
