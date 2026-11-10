"""Índice de documentos: um vetor por documento (ficha + início do texto) para encontrar documentos
semelhantes a um tema ou a outro documento. Vive numa coleção do Chroma à parte da dos excertos."""

import logging

from backend.models import DocumentInfo, DocumentMetadata
from backend.services.document_types import DocumentType
from backend.services.embeddings import embed_texts
from backend.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

FALLBACK_CHARS = 1500


def profile_text(metadata: DocumentMetadata, body: str) -> str:
    """Título, palavras-chave e resumo; sem resumo, o início do corpo do documento faz as vezes dele."""
    parts = [metadata.title, "; ".join(metadata.keywords), metadata.abstract or body[:FALLBACK_CHARS]]
    return "\n".join(part for part in parts if part.strip())


def profile_metadata(info: DocumentInfo, metadata: DocumentMetadata, doc_type: DocumentType) -> dict:
    """Metadados escalares (o Chroma não aceita listas nem None), com os mesmos nomes dos excertos para os
    mesmos filtros funcionarem nas duas coleções."""
    values = {
        "document_id": info.document_id,
        "filename": info.filename,
        "document_type": doc_type.key,
        "title": metadata.title,
        "year": metadata.year,
        **{f.key: metadata.fields.get(f.key) for f in doc_type.fields if f.filterable},
    }
    return {key: value for key, value in values.items() if value}


def upsert_profile(
    store: VectorStore,
    embedding_model: str,
    info: DocumentInfo,
    metadata: DocumentMetadata,
    doc_type: DocumentType,
    body: str,
) -> None:
    text = profile_text(metadata, body)
    if not text.strip():
        return
    store.upsert_chunks(
        ids=[info.document_id],
        embeddings=embed_texts(embedding_model, [text]),
        documents=[text],
        metadatas=[profile_metadata(info, metadata, doc_type)],
    )
