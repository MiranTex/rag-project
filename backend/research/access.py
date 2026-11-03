"""Quem pode fazer o quê num projeto, e o contexto (pipeline, índices, fichas) usado pela área de pesquisa."""

from typing import Literal

from fastapi import HTTPException

from backend.agent.tools.base import ToolContext
from backend.auth.permissions import AuthenticatedUser
from backend.config import get_settings
from backend.dependencies import (
    get_document_types,
    get_export_store,
    get_extraction_store,
    get_profile_store,
    get_rag_pipeline,
    get_registry,
    get_research_repository,
    get_vector_store,
)
from backend.research.models import Project

ProjectRole = Literal["owner", "editor", "viewer"]
# O que cada papel no projeto pode fazer: viewer lê e comenta; editor altera o conteúdo; owner gere membros.
_LEVELS = {"viewer": 0, "editor": 1, "owner": 2}


def project_role(project: Project, user_id: str) -> ProjectRole | None:
    if project.owner_id == user_id:
        return "owner"
    for member in get_research_repository().list_members(project.project_id):
        if member.user_id == user_id:
            return member.role
    return None


def load_project(project_id: str, user: AuthenticatedUser, needs: ProjectRole = "viewer") -> tuple[Project, ProjectRole]:
    """404 se o projeto não existe ou a pessoa não é membro (não se revela que existe); 403 se é membro mas o
    papel não chega."""
    project = get_research_repository().get_project(project_id)
    role = project_role(project, user.user_id) if project else None
    if project is None or role is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    if _LEVELS[role] < _LEVELS[needs]:
        raise HTTPException(status_code=403, detail="O teu papel neste projeto não permite esta operação.")
    return project, role


def project_document_ids(project_id: str) -> list[str]:
    """Documentos fixados que continuam indexados (um documento removido ou em revisão deixa de contar)."""
    registry = get_registry()
    ids = []
    for pinned in get_research_repository().list_project_documents(project_id):
        info = registry.find_by_id(pinned.document_id)
        if info and info.status == "indexed":
            ids.append(pinned.document_id)
    return ids


def project_scope(project_id: str | None, user: AuthenticatedUser) -> list[str] | None:
    """Documentos a que uma pesquisa fica limitada: os do projeto, ou None (toda a base) sem projeto."""
    if not project_id:
        return None
    load_project(project_id, user)
    ids = project_document_ids(project_id)
    if not ids:
        raise HTTPException(status_code=400, detail="O projeto ainda não tem documentos fixados.")
    return ids


def research_context(user: AuthenticatedUser, scope: list[str] | None = None) -> ToolContext:
    settings = get_settings()
    return ToolContext(
        pipeline=get_rag_pipeline(),
        vector_store=get_vector_store(),
        registry=get_registry(),
        export_store=get_export_store().for_owner(user.user_id),
        top_k=settings.top_k,
        extraction_store=get_extraction_store(),
        document_types=get_document_types(),
        profile_store=get_profile_store(),
        embedding_model=settings.embedding_model,
        scope_document_ids=scope,
    )
