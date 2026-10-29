import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.config import get_settings
from backend.dependencies import get_extraction_store, get_keyword_index, get_registry, get_vector_store
from backend.models import (
    DocumentExtraction,
    DocumentInfo,
    PageAlert,
    PageOcrRequest,
    PageUpdateRequest,
    ReviewPage,
    UploadResponse,
)
from backend.services.embeddings import embed_texts
from backend.services.extraction_review import validate_page
from backend.services.ocr import ocr_image, render_page
from backend.services.pdf_ingestion import (
    chunk_pages,
    count_pages,
    extract_pages,
    file_sha256,
    save_uploaded_file,
    utc_now_iso,
)

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

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


def _extract_for_review(document_id: str, filename: str, raw: bytes) -> tuple[DocumentInfo, list[ReviewPage]]:
    """Fase 1: extrai o texto (pypdf + OCR), valida cada página e deixa o documento à espera de revisão."""
    settings = get_settings()
    started = time.perf_counter()
    logger.info("A extrair %s (%s)", filename, document_id)
    saved_path = save_uploaded_file(settings.upload_dir, filename, raw)
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

    # O documento sai do índice até ser aprovado: a pesquisa nunca usa texto por rever.
    get_vector_store().delete_document(document_id)
    get_keyword_index().remove_document(document_id)
    get_extraction_store().save(document_id, pages)

    info = _with_counts(
        DocumentInfo(
            document_id=document_id,
            filename=Path(filename).name,
            sha256=file_sha256(raw),
            created_at=utc_now_iso(),
            chunk_count=0,
            status="pending_review",
        ),
        pages,
    )
    get_registry().add_or_replace(info)
    logger.info(
        "%s extraído em %.1fs: %d página(s), %d alerta(s)",
        filename,
        time.perf_counter() - started,
        info.page_count,
        info.alert_count,
    )
    return info, pages


def _approve(info: DocumentInfo, pages: list[ReviewPage]) -> DocumentInfo:
    """Fase 2: indexa o texto revisto (chunks, embeddings, Chroma e índice de palavras-chave)."""
    settings = get_settings()
    vector_store = get_vector_store()
    keyword_index = get_keyword_index()

    started = time.perf_counter()
    included = [page for page in pages if not page.excluded and page.text.strip()]
    if not included:
        raise HTTPException(status_code=400, detail="Nenhuma página com texto para indexar.")

    pages_by_number = {page.page: page for page in included}
    chunks = chunk_pages(
        pages=[(page.page, page.text) for page in included],
        document_id=info.document_id,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Não foram gerados chunks válidos.")

    texts = [chunk.text for chunk in chunks]
    logger.info("%s: %d página(s) aprovada(s), %d chunks; a gerar embeddings", info.filename, len(included), len(chunks))
    embeddings = embed_texts(settings.embedding_model, texts)

    vector_store.delete_document(info.document_id)

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
        }
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

    indexed = _with_counts(info, pages).model_copy(update={"chunk_count": len(chunks), "status": "indexed"})
    get_registry().add_or_replace(indexed)
    logger.info("%s indexado em %.1fs", info.filename, time.perf_counter() - started)
    return indexed


def _extract_and_maybe_approve(document_id: str, filename: str, raw: bytes) -> UploadResponse:
    with _locked(document_id):
        info, pages = _extract_for_review(document_id, filename, raw)
        if get_settings().auto_approve_clean_documents and info.alert_count == 0:
            return UploadResponse(
                message="Documento sem alertas: aprovado e indexado automaticamente.",
                document=_approve(info, pages),
            )
    message = (
        f"Texto extraído com {info.alert_count} alerta(s). Rever antes de indexar."
        if info.alert_count
        else "Texto extraído sem alertas. Aguarda aprovação para indexar."
    )
    return UploadResponse(message=message, document=info)


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
    if info.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Documento já indexado. Use reindex para voltar à revisão.",
        )


def _save_page(info: DocumentInfo, pages: list[ReviewPage], updated: ReviewPage) -> DocumentExtraction:
    pages = [updated if page.page == updated.page else page for page in pages]
    get_extraction_store().save(info.document_id, pages)
    info = _with_counts(info, pages)
    get_registry().add_or_replace(info)
    return DocumentExtraction(document=info, pages=pages)


def _find_page(pages: list[ReviewPage], page_number: int) -> ReviewPage:
    for page in pages:
        if page.page == page_number:
            return page
    raise HTTPException(status_code=404, detail="Página não encontrada.")


@router.get("", response_model=list[DocumentInfo])
def list_documents() -> list[DocumentInfo]:
    return get_registry().list_documents()


@router.delete("/{document_id}")
def delete_document(document_id: str) -> dict:
    settings = get_settings()
    registry = get_registry()
    vector_store = get_vector_store()
    keyword_index = get_keyword_index()

    existing = registry.find_by_id(document_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    vector_store.delete_document(document_id)
    keyword_index.remove_document(document_id)
    registry.remove(document_id)
    get_extraction_store().delete(document_id)

    upload_path = Path(settings.upload_dir) / existing.filename
    if upload_path.exists():
        upload_path.unlink()

    return {"message": "Documento removido com sucesso."}


@router.post("/{document_id}/reindex", response_model=UploadResponse)
async def reindex_document(document_id: str) -> UploadResponse:
    settings = get_settings()
    registry = get_registry()

    existing = registry.find_by_id(document_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    upload_path = Path(settings.upload_dir) / existing.filename
    if not upload_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Ficheiro original não encontrado no storage local.",
        )

    raw = upload_path.read_bytes()
    # Volta a extrair do zero: as edições manuais anteriores perdem-se.
    return await run_in_threadpool(_extract_and_maybe_approve, document_id, existing.filename, raw)


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    reindex: bool = Form(False),
) -> UploadResponse:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas ficheiros PDF são suportados.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Ficheiro vazio.")

    settings = get_settings()
    registry = get_registry()

    sha = file_sha256(raw)
    existing = registry.find_by_hash(sha)
    if existing and not reindex:
        return UploadResponse(
            message="Documento já indexado. Use reindex=true para forçar nova indexação.",
            document=existing,
        )

    document_id = existing.document_id if existing else str(uuid4())
    # OCR e embeddings são CPU-bound: correr fora do event loop para não bloquear os outros pedidos.
    return await run_in_threadpool(_extract_and_maybe_approve, document_id, file.filename, raw)


@router.get("/{document_id}/extraction", response_model=DocumentExtraction)
def get_extraction(document_id: str) -> DocumentExtraction:
    info, pages = _get_document_and_pages(document_id)
    return DocumentExtraction(document=info, pages=pages)


@router.put("/{document_id}/pages/{page_number}", response_model=DocumentExtraction)
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


@router.post("/{document_id}/pages/{page_number}/ocr", response_model=DocumentExtraction)
async def rerun_page_ocr(document_id: str, page_number: int, payload: PageOcrRequest) -> DocumentExtraction:
    settings = get_settings()
    dpi = payload.dpi or settings.ocr_dpi

    def run() -> DocumentExtraction:
        with _locked(document_id):
            info, pages = _get_document_and_pages(document_id)
            _require_pending(info)
            page = _find_page(pages, page_number)

            upload_path = Path(settings.upload_dir) / info.filename
            if not upload_path.exists():
                raise HTTPException(status_code=404, detail="Ficheiro original não encontrado no storage local.")

            result = ocr_image(render_page(upload_path, page_number, dpi), settings.ocr_languages)
            text = " ".join(result.text.split())
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


@router.post("/{document_id}/approve", response_model=UploadResponse)
async def approve_document(document_id: str) -> UploadResponse:
    def run() -> DocumentInfo:
        with _locked(document_id):
            info, pages = _get_document_and_pages(document_id)
            _require_pending(info)
            return _approve(info, pages)

    indexed = await run_in_threadpool(run)
    return UploadResponse(message="Documento aprovado e indexado.", document=indexed)
