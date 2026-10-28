import logging
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.config import get_settings
from backend.dependencies import get_keyword_index, get_registry, get_vector_store
from backend.models import DocumentInfo, UploadResponse
from backend.services.embeddings import embed_texts
from backend.services.pdf_ingestion import (
    chunk_pages,
    extract_pages,
    file_sha256,
    save_uploaded_file,
    utc_now_iso,
)

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

_indexing_ids: set[str] = set()
_indexing_lock = threading.Lock()


def _index_pdf_content(
    document_id: str,
    filename: str,
    raw: bytes,
) -> DocumentInfo:
    with _indexing_lock:
        if document_id in _indexing_ids:
            raise HTTPException(status_code=409, detail="Documento já está a ser indexado.")
        _indexing_ids.add(document_id)
    try:
        return _index_pdf_content_unlocked(document_id, filename, raw)
    finally:
        with _indexing_lock:
            _indexing_ids.discard(document_id)


def _index_pdf_content_unlocked(
    document_id: str,
    filename: str,
    raw: bytes,
) -> DocumentInfo:
    settings = get_settings()
    registry = get_registry()
    vector_store = get_vector_store()
    keyword_index = get_keyword_index()

    started = time.perf_counter()
    logger.info("A indexar %s (%s)", filename, document_id)
    saved_path = save_uploaded_file(settings.upload_dir, filename, raw)
    pages = extract_pages(
        saved_path,
        ocr_languages=settings.ocr_languages if settings.ocr_enabled else None,
        ocr_dpi=settings.ocr_dpi,
        ocr_min_text_chars=settings.ocr_min_text_chars,
        ocr_min_confidence=settings.ocr_min_confidence,
        ocr_max_workers=settings.ocr_max_workers,
    )

    if not pages:
        raise HTTPException(status_code=400, detail="Não foi possível extrair texto do PDF.")

    pages_by_number = {page.page: page for page in pages}
    chunks = chunk_pages(
        pages=[(page.page, page.text) for page in pages],
        document_id=document_id,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Não foram gerados chunks válidos.")

    texts = [chunk.text for chunk in chunks]
    logger.info("%s: %d página(s) com texto, %d chunks; a gerar embeddings", filename, len(pages), len(chunks))
    embeddings = embed_texts(settings.embedding_model, texts)

    vector_store.delete_document(document_id)

    metadatas: list[dict] = []
    keyword_chunks: list[dict] = []
    for chunk in chunks:
        metadata = {
            "document_id": document_id,
            "filename": Path(filename).name,
            "page": chunk.page,
            "chunk_index": chunk.chunk_index,
            "document_chunk_count": chunk.document_chunk_count,
            "extraction": pages_by_number[chunk.page].source,
        }
        if pages_by_number[chunk.page].ocr_confidence is not None:
            metadata["ocr_confidence"] = pages_by_number[chunk.page].ocr_confidence
        metadatas.append(metadata)
        keyword_chunks.append({"text": chunk.text, "metadata": metadata})

    vector_store.upsert_chunks(
        ids=[chunk.id for chunk in chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    keyword_index.index_document(document_id, keyword_chunks)

    info = DocumentInfo(
        document_id=document_id,
        filename=Path(filename).name,
        sha256=file_sha256(raw),
        created_at=utc_now_iso(),
        chunk_count=len(chunks),
    )
    registry.add_or_replace(info)
    logger.info("%s indexado em %.1fs", filename, time.perf_counter() - started)
    return info


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
    info = await run_in_threadpool(_index_pdf_content, document_id, existing.filename, raw)
    return UploadResponse(message="Documento reindexado com sucesso.", document=info)


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
    info = await run_in_threadpool(_index_pdf_content, document_id, file.filename, raw)

    return UploadResponse(message="Documento indexado com sucesso.", document=info)
