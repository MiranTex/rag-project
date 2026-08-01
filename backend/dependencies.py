from functools import lru_cache

from backend.config import get_settings
from backend.services.document_registry import DocumentRegistry
from backend.services.keyword_index import KeywordIndex
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
def get_keyword_index() -> KeywordIndex:
    settings = get_settings()
    index = KeywordIndex(k1=settings.keyword_bm25_k1, b=settings.keyword_bm25_b)
    index.rebuild(get_vector_store().list_chunks())
    return index


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
        keyword_index=get_keyword_index(),
        lmstudio_client=get_lmstudio_client(),
        rerank_weights=settings.parse_rerank_weights("default"),
        retrieval_mode_default=settings.retrieval_mode_default,
        keyword_candidate_multiplier=settings.keyword_candidate_multiplier,
    )
