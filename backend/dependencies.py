from functools import lru_cache

from backend.config import get_settings
from backend.services.document_registry import DocumentRegistry
from backend.services.lmstudio_client import LMStudioClient
from backend.services.rag_pipeline import RagPipeline
from backend.services.vector_store import VectorStore


@lru_cache(maxsize=1)
def get_registry() -> DocumentRegistry:
    return DocumentRegistry()


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.chroma_collection,
    )


@lru_cache(maxsize=1)
def get_lmstudio_client() -> LMStudioClient:
    settings = get_settings()
    return LMStudioClient(
        base_url=settings.lm_studio_base_url,
        model=settings.lm_studio_chat_model,
    )


@lru_cache(maxsize=1)
def get_rag_pipeline() -> RagPipeline:
    settings = get_settings()
    return RagPipeline(
        embedding_model=settings.embedding_model,
        vector_store=get_vector_store(),
        lmstudio_client=get_lmstudio_client(),
        rerank_weights=settings.parse_rerank_weights("default"),
    )
