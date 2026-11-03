import hashlib
import json
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.api.security import require
from backend.auth.permissions import (
    DOCUMENTS_APPROVE,
    DOCUMENTS_READ,
    DOCUMENTS_REVIEW,
    DOCUMENTS_UPLOAD,
    AuthenticatedUser,
)
from backend.config import get_settings
from backend.dependencies import (
    NON_CONTENT_SECTIONS,
    get_document_types,
    get_extraction_store,
    get_job_queue,
    get_keyword_index,
    get_profile_store,
    get_registry,
    get_renamer,
    get_utility_llm,
    get_vector_store,
)
from backend.models import (
    DocumentExtraction,
    DocumentInfo,
    DocumentMetadata,
    DocumentTypeField,
    DocumentTypeInfo,
    Job,
    MetadataUpdate,
    PageAlert,
    PageOcrRequest,
    PageUpdateRequest,
    RenameRequest,
    ReviewPage,
    SectionHeading,
    UploadResponse,
)
from backend.services.document_profiles import upsert_profile
from backend.services.document_renamer import RenameError
from backend.services.document_structure import Heading, Segment, find_references, split_sections
from backend.services.document_naming import clean_name, unique_name
from backend.services.document_types import DocumentType, section_label
from backend.services.embeddings import embed_texts
from backend.services.extraction_review import validate_page
from backend.services.job_runner import JobRunner
from backend.services.metadata_extraction import clean_fields, propose_metadata
from backend.services.ocr import ocr_image, render_page
from backend.services.pdf_ingestion import (
    chunk_pages,
    count_pages,
    normalize_text,
    extract_pages,
    file_sha256,
    save_uploaded_file,
    utc_now_iso,
)

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

can_read = require(DOCUMENTS_READ)
can_upload = require(DOCUMENTS_UPLOAD)
can_review = require(DOCUMENTS_REVIEW)
can_approve = require(DOCUMENTS_APPROVE)

_indexing_ids: set[str] = set()
_indexing_lock = threading.Lock()


@contextmanager
def _locked(document_id: str) -> Iterator[None]:
    """Impede que o mesmo documento seja extraído, editado ou aprovado em paralelo."""
    with _indexing_lock:
        if document_id in _indexing_ids:
            raise HTTPException(status_code=409, detail="Documento já está a ser processado.")
        _indexing_ids.add(document_id)
    try:
        yield
    finally:
        with _indexing_lock:
            _indexing_ids.discard(document_id)


def _validate(text: str, source: str, ocr_confidence: float | None) -> list[PageAlert]:
    settings = get_settings()
    return validate_page(
        text,
        source,
        ocr_confidence,
        min_text_chars=settings.ocr_min_text_chars,
        min_confidence=settings.ocr_min_confidence,
        max_garbled_ratio=settings.review_max_garbled_ratio,
    )


def _with_counts(info: DocumentInfo, pages: list[ReviewPage]) -> DocumentInfo:
    alert_count = sum(len(page.alerts) for page in pages if not page.excluded)
    return info.model_copy(update={"page_count": len(pages), "alert_count": alert_count})


def _with_metadata(info: DocumentInfo, metadata: DocumentMetadata) -> DocumentInfo:
    return info.model_copy(update={"title": metadata.title, "year": metadata.year, "document_type": metadata.document_type})


def _document_type(metadata: DocumentMetadata) -> DocumentType:
    return get_document_types().get(metadata.document_type)


def _structure(pages: list[ReviewPage], doc_type: DocumentType) -> tuple[list[Segment], list[Heading]]:
    """Secções do texto revisto (só páginas incluídas e com texto), com os títulos do tipo de documento."""
    included = [(page.page, page.text) for page in pages if not page.excluded and page.text.strip()]
    return split_sections(included, doc_type.sections)


def _propose_metadata(pages: list[ReviewPage]) -> DocumentMetadata:
    settings = get_settings()
    llm = get_utility_llm() if settings.metadata_extraction_enabled else None
    return propose_metadata(
        [(page.page, page.text) for page in pages if page.text.strip()],
        get_document_types(),
        llm,
        settings.knowledge_base_description,
    )


def _taken_names(document_id: str) -> set[str]:
    return {d.filename for d in get_registry().list_documents() if d.document_id != document_id}


def _stored_path(info: DocumentInfo) -> Path:
    return Path(get_settings().upload_dir) / (info.storage_name or info.filename)


def _drop_legacy_file(previous: DocumentInfo, stored_name: str) -> None:
    """Documentos antigos estavam em disco com o nome original; depois de copiados para <id>.pdf, o ficheiro
    antigo só se apaga se nenhum outro documento o usar (dois uploads com o mesmo nome partilhavam-no)."""
    legacy = previous.storage_name or previous.filename
    if legacy == stored_name:
        return
    in_use = any(
        (d.storage_name or d.filename) == legacy for d in get_registry().list_documents() if d.document_id != previous.document_id
    )
    if not in_use:
        (Path(get_settings().upload_dir) / legacy).unlink(missing_ok=True)


def _fingerprint(pages: list[ReviewPage]) -> str:
    """Resume o texto que vai para o índice (páginas incluídas, com o texto final de cada uma)."""
    included = [[page.page, page.text] for page in pages if not page.excluded]
    return hashlib.sha256(json.dumps(included, ensure_ascii=False).encode()).hexdigest()


def _build_extraction(info: DocumentInfo, pages: list[ReviewPage]) -> DocumentExtraction:
    metadata = get_extraction_store().load_metadata(info.document_id)
    doc_type = _document_type(metadata)
    segments, headings = _structure(pages, doc_type)
    return DocumentExtraction(
        document=info,
        pages=pages,
        metadata=metadata,
        sections=[
            SectionHeading(section=h.section, label=section_label(doc_type, h.section), page=h.page, text=h.text)
            for h in headings
        ],
        references=find_references(segments),
        suggested_name=get_renamer().suggestion(info, metadata),
    )


def _extract_for_review(info: DocumentInfo, is_new: bool) -> tuple[DocumentInfo, list[ReviewPage], bool]:
    """Fase 1 (em background): extrai o texto (pypdf + OCR), valida cada página, propõe a ficha e deixa o
    documento à espera de revisão. O nome automático só se decide num upload novo (is_new).

    Devolve também se o texto é igual ao da última versão aprovada: nesse caso a ficha revista mantém-se
    (não se propõe outra) e o documento pode voltar ao índice sem nova aprovação."""
    settings = get_settings()
    started = time.perf_counter()
    document_id = info.document_id
    logger.info("A extrair %s (%s)", info.original_filename or info.filename, document_id)

    # O documento sai do índice antes de tudo: a pesquisa nunca usa texto por rever nem uma extração a meio.
    get_vector_store().delete_document(document_id)
    get_keyword_index().remove_document(document_id)
    get_profile_store().delete_document(document_id)

    saved_path = _stored_path(info)
    extracted = {
        page.page: page
        for page in extract_pages(
            saved_path,
            ocr_languages=settings.ocr_languages if settings.ocr_enabled else None,
            ocr_dpi=settings.ocr_dpi,
            ocr_min_text_chars=settings.ocr_min_text_chars,
            ocr_min_confidence=settings.ocr_min_confidence,
            ocr_max_workers=settings.ocr_max_workers,
        )
    }

    # Páginas sem texto também entram na revisão, para se poder escrever o texto à mão.
    pages: list[ReviewPage] = []
    for number in range(1, count_pages(saved_path) + 1):
        page = extracted.get(number)
        text = page.text if page else ""
        source = page.source if page else "none"
        confidence = page.ocr_confidence if page else None
        pages.append(
            ReviewPage(
                page=number,
                text=text,
                source=source,
                ocr_confidence=confidence,
                alerts=_validate(text, source, confidence),
            )
        )

    get_extraction_store().save(document_id, pages)
    unchanged = not is_new and bool(info.approved_fingerprint) and _fingerprint(pages) == info.approved_fingerprint
    if unchanged:
        metadata = get_extraction_store().load_metadata(document_id)
    else:
        metadata = _propose_metadata(pages)
        get_extraction_store().save_metadata(document_id, metadata)

    info = _with_counts(_with_metadata(info, metadata), pages).model_copy(
        update={"status": "pending_review", "chunk_count": 0, "error": ""}
    )
    if is_new:
        info = get_renamer().name_at_upload(info, metadata)
    get_registry().add_or_replace(info)
    logger.info(
        "%s extraído em %.1fs como %s: %d página(s), %d alerta(s), ficha %s",
        info.original_filename or document_id,
        time.perf_counter() - started,
        info.filename,
        info.page_count,
        info.alert_count,
        "mantida (texto igual ao aprovado)" if unchanged else "proposta" if metadata.auto_filled else "por preencher",
    )
    return info, pages, unchanged


def _approve(info: DocumentInfo, pages: list[ReviewPage], approved_by: str) -> DocumentInfo:
    """Fase 2: indexa o texto revisto (chunks, embeddings, Chroma e índice de palavras-chave)."""
    settings = get_settings()
    vector_store = get_vector_store()
    keyword_index = get_keyword_index()

    started = time.perf_counter()
    included = [page for page in pages if not page.excluded and page.text.strip()]
    if not included:
        raise HTTPException(status_code=400, detail="Nenhuma página com texto para indexar.")

    pages_by_number = {page.page: page for page in included}
    store = get_extraction_store()
    doc_type = _document_type(store.load_metadata(info.document_id))
    segments, headings = _structure(pages, doc_type)
    chunks = chunk_pages(
        pages=[(segment.page, segment.text, segment.section) for segment in segments],
        document_id=info.document_id,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Não foram gerados chunks válidos.")

    texts = [chunk.text for chunk in chunks]
    logger.info(
        "%s: %d página(s) aprovada(s), %d secção(ões), %d chunks; a gerar embeddings",
        info.filename,
        len(included),
        len(headings),
        len(chunks),
    )
    embeddings = embed_texts(settings.embedding_model, texts)

    vector_store.delete_document(info.document_id)

    # As referências gravadas são as do texto aprovado (incluindo correções feitas na revisão).
    document_metadata = store.load_metadata(info.document_id).model_copy(update={"references": find_references(segments)})
    store.save_metadata(info.document_id, document_metadata)
    # O Chroma só aceita valores escalares e não aceita None: só entram os campos preenchidos.
    # Dos campos próprios do tipo, só os marcados como filterable (servem para filtrar pesquisas).
    document_fields = {
        key: value
        for key, value in {
            "document_type": doc_type.key,
            "title": document_metadata.title,
            "year": document_metadata.year,
            **{f.key: document_metadata.fields.get(f.key) for f in doc_type.fields if f.filterable},
        }.items()
        if value
    }

    metadatas: list[dict] = []
    keyword_chunks: list[dict] = []
    for chunk in chunks:
        page = pages_by_number[chunk.page]
        metadata = {
            "document_id": info.document_id,
            "filename": info.filename,
            "page": chunk.page,
            "chunk_index": chunk.chunk_index,
            "document_chunk_count": chunk.document_chunk_count,
            "extraction": page.source,
            "edited": page.edited,
            **document_fields,
        }
        if chunk.section:
            metadata["section"] = chunk.section
        if page.ocr_confidence is not None:
            metadata["ocr_confidence"] = page.ocr_confidence
        metadatas.append(metadata)
        keyword_chunks.append({"text": chunk.text, "metadata": metadata})

    vector_store.upsert_chunks(
        ids=[chunk.id for chunk in chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    keyword_index.index_document(info.document_id, keyword_chunks)
    body = " ".join(segment.text for segment in segments if segment.section not in NON_CONTENT_SECTIONS)
    upsert_profile(get_profile_store(), settings.embedding_model, info, document_metadata, doc_type, body)

    indexed = _with_metadata(_with_counts(info, pages), document_metadata).model_copy(
        update={
            "chunk_count": len(chunks),
            "status": "indexed",
            "approved_by": approved_by,
            "approved_fingerprint": _fingerprint(pages),
        }
    )
    get_registry().add_or_replace(indexed)
    logger.info("%s indexado em %.1fs", info.filename, time.perf_counter() - started)
    return indexed


def _run_extract_job(job: Job) -> None:
    info = get_registry().find_by_id(job.document_id)
    if info is None:
        return  # removido enquanto esperava na fila
    info, pages, unchanged = _extract_for_review(info, is_new=bool(job.payload.get("new")))
    settings = get_settings()
    # Texto igual ao aprovado: volta ao índice com a aprovação anterior. Senão, a auto-aprovação (sem alertas)
    # só se aplica quando não é obrigatório outra pessoa aprovar.
    if unchanged:
        approved_by = info.approved_by
    elif settings.auto_approve_clean_documents and not settings.require_separate_approver and info.alert_count == 0:
        approved_by = ""
    else:
        return
    try:
        _approve(info, pages, approved_by)
    except Exception as exc:
        # A extração correu bem: o documento fica em revisão, com o motivo, em vez de "failed".
        logger.exception("Indexação automática de %s falhou", info.filename)
        get_registry().add_or_replace(info.model_copy(update={"error": f"Indexação automática falhou: {exc}"}))


def _run_index_job(job: Job) -> None:
    info, pages = _get_document_and_pages(job.document_id)
    _approve(info, pages, job.payload.get("approved_by", ""))


def _on_job_failure(job: Job, message: str) -> None:
    info = get_registry().find_by_id(job.document_id)
    if info is None:
        return
    # Indexação falhada: volta à revisão (o texto revisto continua lá) para se aprovar de novo.
    # Extração falhada: "failed", até alguém extrair de novo ou remover.
    status = "pending_review" if job.kind == "index" else "failed"
    get_registry().add_or_replace(info.model_copy(update={"status": status, "error": message}))


JOB_HANDLERS = {"extract": _run_extract_job, "index": _run_index_job}


def build_job_runner() -> JobRunner:
    return JobRunner(get_job_queue(), JOB_HANDLERS, _on_job_failure, get_settings().job_poll_seconds)


def _enqueue(info: DocumentInfo, kind: str, status: str, payload: dict | None = None) -> DocumentInfo:
    """Põe o documento na fila (um trabalho de cada vez por documento) e regista o estado novo."""
    queue = get_job_queue()
    if queue.active_for_document(info.document_id):
        raise HTTPException(status_code=409, detail="Documento já está a ser processado.")
    updated = info.model_copy(update={"status": status, "error": ""})
    get_registry().add_or_replace(updated)
    queue.enqueue(kind, info.document_id, payload)
    return updated


def _get_document_and_pages(document_id: str) -> tuple[DocumentInfo, list[ReviewPage]]:
    info = get_registry().find_by_id(document_id)
    if not info:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    pages = get_extraction_store().load(document_id)
    if pages is None:
        raise HTTPException(
            status_code=404,
            detail="Extração não encontrada (documento indexado antes da fase de revisão). Use reindex.",
        )
    return info, pages


def _require_pending(info: DocumentInfo) -> None:
    if info.status in ("extracting", "indexing"):
        raise HTTPException(status_code=409, detail="Documento a ser processado. Tenta de novo quando terminar.")
    if info.status != "pending_review":
        raise HTTPException(status_code=409, detail="Documento já indexado. Use reindex para voltar à revisão.")


def _save_page(info: DocumentInfo, pages: list[ReviewPage], updated: ReviewPage) -> DocumentExtraction:
    pages = [updated if page.page == updated.page else page for page in pages]
    get_extraction_store().save(info.document_id, pages)
    info = _with_counts(info, pages)
    get_registry().add_or_replace(info)
    return _build_extraction(info, pages)


def _find_page(pages: list[ReviewPage], page_number: int) -> ReviewPage:
    for page in pages:
        if page.page == page_number:
            return page
    raise HTTPException(status_code=404, detail="Página não encontrada.")


@router.get("", response_model=list[DocumentInfo], dependencies=[Depends(can_read)])
def list_documents() -> list[DocumentInfo]:
    return get_registry().list_documents()


@router.delete("/{document_id}", dependencies=[Depends(can_upload)])
def delete_document(document_id: str) -> dict:
    settings = get_settings()
    registry = get_registry()
    vector_store = get_vector_store()
    keyword_index = get_keyword_index()

    existing = registry.find_by_id(document_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    queue = get_job_queue()
    active = queue.active_for_document(document_id)
    if active and active.status == "running":
        raise HTTPException(status_code=409, detail="Documento a ser processado. Tenta de novo quando terminar.")
    queue.cancel_queued(document_id)

    vector_store.delete_document(document_id)
    keyword_index.remove_document(document_id)
    get_profile_store().delete_document(document_id)
    registry.remove(document_id)
    get_extraction_store().delete(document_id)

    upload_path = _stored_path(existing)
    if upload_path.exists():
        upload_path.unlink()

    return {"message": "Documento removido com sucesso."}


def _reextract(existing: DocumentInfo, user: AuthenticatedUser) -> UploadResponse:
    upload_path = _stored_path(existing)
    if not upload_path.exists():
        raise HTTPException(status_code=404, detail="Ficheiro original não encontrado no storage local.")
    with _locked(existing.document_id):
        # Documentos antigos estão em disco com o nome original: passam para <id>.pdf.
        stored_name = f"{existing.document_id}.pdf"
        if (existing.storage_name or existing.filename) != stored_name:
            save_uploaded_file(get_settings().upload_dir, stored_name, upload_path.read_bytes())
            _drop_legacy_file(existing, stored_name)
            existing = existing.model_copy(
                update={"storage_name": stored_name, "original_filename": existing.original_filename or existing.filename}
            )
        # Volta a extrair do zero: as edições manuais anteriores perdem-se; o nome mantém-se.
        # Quem extrai de novo passa a ser quem pôs esta versão em revisão (conta para a aprovação separada).
        existing = existing.model_copy(update={"uploaded_by": user.user_id})
        info = _enqueue(existing, "extract", "extracting", {"new": False})
    return UploadResponse(message="Na fila para extrair de novo.", document=info)


@router.post("/{document_id}/reindex", response_model=UploadResponse)
def reindex_document(document_id: str, user: AuthenticatedUser = Depends(can_upload)) -> UploadResponse:
    existing = get_registry().find_by_id(document_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return _reextract(existing, user)


ALREADY_UPLOADED = {
    "extracting": "Este documento já está a ser extraído.",
    "pending_review": "Este documento já foi carregado e aguarda revisão.",
    "indexing": "Este documento já está a ser indexado.",
    "indexed": "Este documento já está indexado.",
    "failed": "Este documento já foi carregado mas a extração falhou; usa Extrair de novo.",
}


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    reindex: bool = Form(False),
    user: AuthenticatedUser = Depends(can_upload),
) -> UploadResponse:
    """Guarda o PDF e põe-no na fila de extração; a resposta não espera pelo OCR."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas ficheiros PDF são suportados.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Ficheiro vazio.")

    settings = get_settings()
    sha = file_sha256(raw)
    existing = get_registry().find_by_hash(sha)
    if existing and reindex:
        return _reextract(existing, user)
    if existing:
        return UploadResponse(message=ALREADY_UPLOADED.get(existing.status, "Documento já carregado."), document=existing)

    document_id = str(uuid4())
    stored_name = f"{document_id}.pdf"
    # Em disco pelo id: o nome no sistema pode mudar e dois ficheiros com o mesmo nome não se sobrepõem.
    save_uploaded_file(settings.upload_dir, stored_name, raw)
    original = Path(file.filename).name
    info = DocumentInfo(
        document_id=document_id,
        filename=unique_name(clean_name(original) or original, _taken_names(document_id)),
        original_filename=original,
        storage_name=stored_name,
        sha256=sha,
        created_at=utc_now_iso(),
        chunk_count=0,
        status="extracting",
        uploaded_by=user.user_id,
    )
    with _locked(document_id):
        info = _enqueue(info, "extract", "extracting", {"new": True})
    return UploadResponse(message="Na fila para extração.", document=info)


@router.get("/{document_id}/extraction", response_model=DocumentExtraction, dependencies=[Depends(can_read)])
def get_extraction(document_id: str) -> DocumentExtraction:
    info, pages = _get_document_and_pages(document_id)
    return _build_extraction(info, pages)


@router.put("/{document_id}/pages/{page_number}", response_model=DocumentExtraction, dependencies=[Depends(can_review)])
def update_page(document_id: str, page_number: int, payload: PageUpdateRequest) -> DocumentExtraction:
    with _locked(document_id):
        info, pages = _get_document_and_pages(document_id)
        _require_pending(info)
        page = _find_page(pages, page_number)

        update: dict = {}
        if payload.excluded is not None:
            update["excluded"] = payload.excluded
        if payload.text is not None and payload.text != page.text:
            # Texto corrigido à mão: a confiança do OCR deixa de se aplicar, mas as outras verificações correm de novo.
            update.update(text=payload.text, source="manual", edited=True, alerts=_validate(payload.text, "manual", None))
        return _save_page(info, pages, page.model_copy(update=update))


@router.post(
    "/{document_id}/pages/{page_number}/ocr", response_model=DocumentExtraction, dependencies=[Depends(can_review)]
)
async def rerun_page_ocr(document_id: str, page_number: int, payload: PageOcrRequest) -> DocumentExtraction:
    settings = get_settings()
    dpi = payload.dpi or settings.ocr_dpi

    def run() -> DocumentExtraction:
        with _locked(document_id):
            info, pages = _get_document_and_pages(document_id)
            _require_pending(info)
            page = _find_page(pages, page_number)

            upload_path = _stored_path(info)
            if not upload_path.exists():
                raise HTTPException(status_code=404, detail="Ficheiro original não encontrado no storage local.")

            result = ocr_image(render_page(upload_path, page_number, dpi), settings.ocr_languages)
            text = normalize_text(result.text)
            source = "ocr" if text else "none"
            confidence = result.confidence if text else None
            logger.info("%s p.%d: OCR repetido a %d dpi, confiança %.1f", info.filename, page_number, dpi, result.confidence)
            updated = page.model_copy(
                update={
                    "text": text,
                    "source": source,
                    "ocr_confidence": confidence,
                    "edited": False,
                    "alerts": _validate(text, source, confidence),
                }
            )
            return _save_page(info, pages, updated)

    return await run_in_threadpool(run)


def _clean_text_list(values: list[str]) -> list[str]:
    return [" ".join(value.split()) for value in values if value.strip()]


@router.get("/types", response_model=list[DocumentTypeInfo], dependencies=[Depends(can_read)])
def list_document_types() -> list[DocumentTypeInfo]:
    """Tipos de documento configurados, para o formulário da ficha (o primeiro é o tipo por defeito)."""
    types = get_document_types()
    ordered = [types.types[types.default]] + [t for key, t in types.types.items() if key != types.default]
    return [
        DocumentTypeInfo(
            key=t.key,
            label=t.label,
            description=t.description,
            fields=[DocumentTypeField(key=f.key, label=f.label, type=f.kind, hint=f.hint, filterable=f.filterable) for f in t.fields],
            sections=[{"key": sec.key, "label": sec.label} for sec in t.sections],
        )
        for t in ordered
    ]


@router.put("/{document_id}/metadata", response_model=DocumentExtraction, dependencies=[Depends(can_review)])
def update_metadata(document_id: str, payload: MetadataUpdate) -> DocumentExtraction:
    with _locked(document_id):
        info, pages = _get_document_and_pages(document_id)
        _require_pending(info)
        types = get_document_types()
        if payload.document_type and payload.document_type not in types.types:
            raise HTTPException(status_code=422, detail=f"Tipo de documento desconhecido: {payload.document_type}")
        doc_type = types.get(payload.document_type)
        store = get_extraction_store()
        metadata = store.load_metadata(document_id).model_copy(
            update={
                "document_type": doc_type.key,
                "title": " ".join(payload.title.split()),
                "authors": _clean_text_list(payload.authors),
                "year": payload.year,
                "keywords": _clean_text_list(payload.keywords),
                "abstract": payload.abstract.strip(),
                # Ao mudar de tipo, os campos que o novo tipo não tem desaparecem.
                "fields": clean_fields(doc_type, payload.fields),
            }
        )
        store.save_metadata(document_id, metadata)
        info = _with_metadata(info, metadata)
        get_registry().add_or_replace(info)
        return _build_extraction(info, pages)


@router.post("/{document_id}/metadata/suggest", response_model=DocumentExtraction, dependencies=[Depends(can_review)])
async def suggest_metadata(document_id: str) -> DocumentExtraction:
    """Volta a propor a ficha (útil se o LLM estava em baixo na extração). Só preenche campos vazios,
    para não apagar correções feitas à mão."""

    def run() -> DocumentExtraction:
        with _locked(document_id):
            info, pages = _get_document_and_pages(document_id)
            _require_pending(info)
            store = get_extraction_store()
            current = store.load_metadata(document_id)
            proposed = _propose_metadata(pages)
            if not proposed.auto_filled:
                raise HTTPException(status_code=502, detail="Não foi possível obter uma proposta do modelo.")
            # O tipo só muda se nunca houve proposta do modelo (ficou o tipo por defeito).
            document_type = current.document_type if current.auto_filled and current.document_type else proposed.document_type
            filled = {
                field: getattr(proposed, field)
                for field in ("title", "authors", "year", "keywords", "abstract")
                if not getattr(current, field) and getattr(proposed, field)
            }
            fields = dict(current.fields) if document_type == current.document_type else {}
            for key, value in proposed.fields.items():
                fields.setdefault(key, value)
            doc_type = get_document_types().get(document_type)
            metadata = current.model_copy(
                update={**filled, "document_type": doc_type.key, "fields": clean_fields(doc_type, fields), "auto_filled": True}
            )
            store.save_metadata(document_id, metadata)
            info = _with_metadata(info, metadata)
            get_registry().add_or_replace(info)
            return _build_extraction(info, pages)

    return await run_in_threadpool(run)


@router.put("/{document_id}/name", response_model=DocumentInfo, dependencies=[Depends(can_review)])
def rename_document(document_id: str, payload: RenameRequest) -> DocumentInfo:
    """Muda o nome do documento no sistema; sem nome, volta ao sugerido pela ficha. Funciona também em
    documentos indexados (o nome muda nas fontes e citações)."""
    if get_registry().find_by_id(document_id) is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    with _locked(document_id):
        try:
            return get_renamer().rename(document_id, payload.name, get_extraction_store().load_metadata(document_id))
        except RenameError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{document_id}/approve", response_model=UploadResponse)
def approve_document(document_id: str, user: AuthenticatedUser = Depends(can_approve)) -> UploadResponse:
    """Põe o texto revisto na fila de indexação (chunks, embeddings, Chroma)."""
    with _locked(document_id):
        info, pages = _get_document_and_pages(document_id)
        _require_pending(info)
        if get_settings().require_separate_approver and info.uploaded_by == user.user_id:
            raise HTTPException(status_code=403, detail="Quem pôs o documento em revisão não o pode aprovar.")
        if not any(not page.excluded and page.text.strip() for page in pages):
            raise HTTPException(status_code=400, detail="Nenhuma página com texto para indexar.")
        info = _enqueue(info, "index", "indexing", {"approved_by": user.user_id})
    return UploadResponse(message="Aprovado. Na fila para indexação.", document=info)
