from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

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


def _index_pdf_content(
    document_id: str,
    filename: str,
    raw: bytes,
) -> DocumentInfo:
    settings = get_settings()
    registry = get_registry()
    vector_store = get_vector_store()
    keyword_index = get_keyword_index()

    saved_path = save_uploaded_file(settings.upload_dir, filename, raw)
    pages = extract_pages(saved_path)

    if not pages:
        raise HTTPException(status_code=400, detail="Não foi possível extrair texto do PDF.")

    chunks = chunk_pages(
        pages=pages,
        document_id=document_id,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Não foram gerados chunks válidos.")

    texts = [chunk.text for chunk in chunks]
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
        }
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
def reindex_document(document_id: str) -> UploadResponse:
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
    info = _index_pdf_content(document_id=document_id, filename=existing.filename, raw=raw)
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
    info = _index_pdf_content(document_id=document_id, filename=file.filename, raw=raw)

    return UploadResponse(message="Documento indexado com sucesso.", document=info)
