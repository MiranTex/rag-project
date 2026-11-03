"""Área de pesquisa fora dos projetos: pesquisa com filtros, leitor de documentos, pesquisas guardadas,
descobrir (mapa do tema, lacunas, "isto parece-se com quê?", verificação de afirmações), esqueleto e exportação.

Quem só usa o chat também tem acesso (research:use): vê os documentos indexados através destas funções, como
já os via nas fontes do chat, mas continua sem a lista completa de documentos."""

import io
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from backend.agent.tools.base import ToolError
from backend.api.security import require
from backend.auth.permissions import RESEARCH_USE, AuthenticatedUser
from backend.config import get_settings
from backend.dependencies import (
    get_document_types,
    get_export_store,
    get_extraction_store,
    get_registry,
    get_research_repository,
    get_utility_llm,
)
from backend.research.access import project_scope, research_context
from backend.research.discovery import analyze_text, check_claims, gaps, theme_map
from backend.research.library import document_card, facets, indexed_document, to_search_filters
from backend.research.models import (
    ClaimCheckRequest,
    DocumentCard,
    ExportRequest,
    ResearchFilters,
    SavedSearch,
    SavedSearchCreate,
    SavedSearchView,
    SearchHit,
    SearchRequest,
    SkeletonRequest,
    TopicRequest,
)
from backend.research.writing import skeleton, skeleton_markdown
from backend.services.document_writer import write_docx, write_markdown
from backend.services.embeddings import embed_query
from backend.services.search_filters import SearchFilters

router = APIRouter(prefix="/research", tags=["research"])

can_research = require(RESEARCH_USE)
MAX_DRAFT_BYTES = 15 * 1024 * 1024
MAX_DRAFT_CHARS = 40_000


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _filters(filters: ResearchFilters, scope: list[str] | None) -> SearchFilters:
    try:
        return to_search_filters(filters, get_document_types(), scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _in_thread(function, *args):
    """Embeddings e LLM bloqueiam: correm fora do loop. ToolError (pedido inválido) responde 400."""
    try:
        return await run_in_threadpool(function, *args)
    except ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---- Pesquisa ----


@router.get("/facets", dependencies=[Depends(can_research)])
def search_facets() -> dict:
    return facets(get_registry(), get_extraction_store(), get_document_types())


@router.post("/search", response_model=list[SearchHit])
async def search(payload: SearchRequest, user: AuthenticatedUser = Depends(can_research)) -> list[SearchHit]:
    filters = _filters(payload.filters, project_scope(payload.project_id, user))

    def run() -> list[SearchHit]:
        sources = research_context(user).pipeline.retrieve_sources(question=payload.query, top_k=payload.top_k, filters=filters)
        extractions = get_extraction_store()
        metadata_cache: dict = {}
        hits = []
        for s in sources:
            metadata = metadata_cache.setdefault(s.document_id, extractions.load_metadata(s.document_id))
            hits.append(
                SearchHit(
                    document_id=s.document_id,
                    filename=s.filename,
                    title=metadata.title,
                    year=metadata.year,
                    document_type=metadata.document_type,
                    page=s.page,
                    section=s.section,
                    text=s.text,
                    score=round(float(s.score), 4),
                )
            )
        return hits

    return await _in_thread(run)


# ---- Leitor ----


def _indexed(document_id: str):
    info = indexed_document(get_registry(), document_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return info


@router.get("/documents/{document_id}", response_model=DocumentCard, dependencies=[Depends(can_research)])
def get_document(document_id: str) -> DocumentCard:
    return document_card(_indexed(document_id), get_extraction_store())


@router.get("/documents/{document_id}/pages/{page_number}", dependencies=[Depends(can_research)])
def get_page(document_id: str, page_number: int) -> dict:
    """Texto aprovado de uma página (o que está indexado), para o leitor destacar o excerto citado."""
    info = _indexed(document_id)
    pages = get_extraction_store().load(document_id) or []
    page = next((p for p in pages if p.page == page_number), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    return {
        "document_id": document_id,
        "filename": info.filename,
        "page": page.page,
        "page_count": len(pages),
        "text": "" if page.excluded else page.text,
        "excluded": page.excluded,
    }


@router.get("/documents/{document_id}/pdf", dependencies=[Depends(can_research)])
def get_pdf(document_id: str) -> FileResponse:
    info = _indexed(document_id)
    path = Path(get_settings().upload_dir) / (info.storage_name or info.filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Ficheiro original não encontrado.")
    return FileResponse(path, media_type="application/pdf", filename=info.filename)


# ---- Pesquisas guardadas ----


def _new_documents(search: SavedSearch) -> list[str]:
    """Documentos indexados carregados depois da última visita que passam nos filtros da pesquisa."""
    # As secções filtram excertos, não documentos: aqui contam só os filtros da ficha.
    filters = replace(_filters(ResearchFilters(**search.filters), None), sections=[])
    extractions = get_extraction_store()
    ids = []
    for info in get_registry().list_documents():
        if info.status != "indexed" or info.created_at <= search.last_seen_at:
            continue
        metadata = extractions.load_metadata(info.document_id)
        values = {"document_id": info.document_id, "document_type": metadata.document_type, "year": metadata.year, **metadata.fields}
        if filters.matches(values):
            ids.append(info.document_id)
    return ids


def _own_search(search_id: str, user: AuthenticatedUser) -> SavedSearch:
    search = get_research_repository().get_search(search_id)
    if search is None or search.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada.")
    return search


@router.get("/searches", response_model=list[SavedSearchView])
def list_searches(user: AuthenticatedUser = Depends(can_research)) -> list[SavedSearchView]:
    return [
        SavedSearchView(**s.model_dump(), new_count=len(_new_documents(s)))
        for s in get_research_repository().list_searches(user.user_id)
    ]


@router.post("/searches", response_model=SavedSearchView)
def create_search(payload: SavedSearchCreate, user: AuthenticatedUser = Depends(can_research)) -> SavedSearchView:
    _filters(payload.filters, None)
    now = _now()
    search = SavedSearch(
        search_id=str(uuid4()),
        owner_id=user.user_id,
        name=payload.name.strip(),
        query=payload.query.strip(),
        filters=payload.filters.model_dump(exclude_defaults=True),
        created_at=now,
        last_seen_at=now,
    )
    get_research_repository().save_search(search)
    return SavedSearchView(**search.model_dump())


@router.delete("/searches/{search_id}")
def delete_search(search_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    _own_search(search_id, user)
    get_research_repository().delete_search(search_id)
    return {"message": "Pesquisa apagada."}


@router.get("/searches/{search_id}/new", response_model=list[DocumentCard])
def new_for_search(search_id: str, user: AuthenticatedUser = Depends(can_research)) -> list[DocumentCard]:
    """Documentos novos da pesquisa, os mais próximos do tema primeiro."""
    search = _own_search(search_id, user)
    ids = _new_documents(search)
    if not ids:
        return []
    ctx = research_context(user)
    ranked = ctx.profile_store.query(
        embed_query(ctx.embedding_model, search.query), len(ids), where=SearchFilters(document_ids=ids).to_chroma_where()
    )
    order = [item["metadata"]["document_id"] for item in ranked] + [i for i in ids]
    registry, extractions = get_registry(), get_extraction_store()
    return [document_card(registry.find_by_id(i), extractions) for i in dict.fromkeys(order) if i in ids]


@router.post("/searches/{search_id}/seen", response_model=SavedSearchView)
def mark_search_seen(search_id: str, user: AuthenticatedUser = Depends(can_research)) -> SavedSearchView:
    search = _own_search(search_id, user).model_copy(update={"last_seen_at": _now()})
    get_research_repository().save_search(search)
    return SavedSearchView(**search.model_dump())


# ---- Descobrir ----


@router.post("/map")
async def topic_map(payload: TopicRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    scope = project_scope(payload.project_id, user)
    filters = _filters(payload.filters, scope)
    return await _in_thread(theme_map, payload.topic, filters, payload.max_documents, research_context(user, scope), get_utility_llm())


@router.post("/gaps")
async def topic_gaps(payload: TopicRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    scope = project_scope(payload.project_id, user)
    filters = _filters(payload.filters, scope)
    return await _in_thread(gaps, payload.topic, filters, min(payload.max_documents, 20), research_context(user, scope), get_utility_llm())


def _text_from_upload(name: str, raw: bytes) -> str:
    """Texto de um rascunho carregado (PDF, Word ou texto). Não é guardado em lado nenhum."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    if suffix == ".docx":
        from docx import Document

        return "\n\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
    if suffix in {".txt", ".md"}:
        return raw.decode("utf-8", errors="replace")
    raise HTTPException(status_code=400, detail="Formatos aceites: PDF, Word (.docx), texto (.txt, .md).")


@router.post("/text-analysis")
async def text_analysis(
    text: str = Form(""),
    project_id: str = Form(""),
    file: UploadFile | None = File(None),
    user: AuthenticatedUser = Depends(can_research),
) -> dict:
    """"Isto parece-se com quê?": texto colado ou ficheiro, comparado com a base (sem o guardar)."""
    if file is not None and file.filename:
        raw = await file.read()
        if len(raw) > MAX_DRAFT_BYTES:
            raise HTTPException(status_code=413, detail="Ficheiro demasiado grande (máximo 15 MB).")
        text = await run_in_threadpool(_text_from_upload, file.filename, raw)
    text = text.strip()[:MAX_DRAFT_CHARS]
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Cola ou carrega um texto com pelo menos 50 caracteres.")
    scope = project_scope(project_id or None, user)
    filters = SearchFilters(document_ids=scope)
    result = await _in_thread(analyze_text, text, filters, research_context(user, scope), get_utility_llm())
    return {**result, "characters": len(text)}


@router.post("/check-claims")
async def claims(payload: ClaimCheckRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    scope = project_scope(payload.project_id, user)
    return await _in_thread(check_claims, payload.text, SearchFilters(document_ids=scope), research_context(user, scope), get_utility_llm())


# ---- Escrever ----


@router.post("/skeleton")
async def work_skeleton(payload: SkeletonRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    if payload.work_type and payload.work_type not in get_document_types().types:
        raise HTTPException(status_code=422, detail=f"Tipo de trabalho desconhecido: {payload.work_type}")
    scope = project_scope(payload.project_id, user) if payload.project_id else None
    result = await _in_thread(skeleton, payload.topic, payload.work_type, scope, research_context(user, scope), get_utility_llm())
    return {**result, "markdown": skeleton_markdown(result)}


@router.get("/work-types", dependencies=[Depends(can_research)])
def work_types() -> list[dict]:
    types = get_document_types()
    return [
        {"key": t.key, "label": t.label, "description": t.description, "sections": [s.label for s in t.sections]}
        for t in types.types.values()
    ]


@router.post("/export")
def export(payload: ExportRequest, user: AuthenticatedUser = Depends(can_research)) -> dict:
    """Guarda texto (esqueleto, estado da arte, bibliografia) como Word ou markdown nos exports da pessoa."""
    path = get_export_store().for_owner(user.user_id).reserve_path(payload.title, payload.format)
    writer = write_docx if payload.format == "docx" else write_markdown
    writer(path, payload.title, payload.markdown)
    return {"name": path.name, "format": payload.format}
