from functools import lru_cache

from backend.agent.guard import ScopeGuard
from backend.agent.tools import ToolRegistry, build_registry
from backend.config import get_settings
from backend.services.document_registry import DocumentRegistry
from backend.services.export_store import ExportStore
from backend.services.document_types import DocumentTypes, load_document_types
from backend.services.extraction_review import ExtractionStore
from backend.services.keyword_index import KeywordIndex
from backend.services.lmstudio_client import LMStudioClient
from backend.services.rag_pipeline import RagPipeline
from backend.services.vector_store import VectorStore


@lru_cache(maxsize=1)
def get_registry() -> DocumentRegistry:
    return DocumentRegistry()


@lru_cache(maxsize=1)
def get_document_types() -> DocumentTypes:
    return load_document_types(get_settings().document_types_file)


@lru_cache(maxsize=1)
def get_extraction_store() -> ExtractionStore:
    return ExtractionStore()


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
    if settings.open_router_api_key:
        return LMStudioClient(
            base_url=settings.open_router_base_url,
            model=settings.open_router_chat_model,
            api_key=settings.open_router_api_key,
        )
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


@lru_cache(maxsize=1)
def get_export_store() -> ExportStore:
    return ExportStore(get_settings().export_dir)


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    return build_registry()


@lru_cache(maxsize=1)
def get_utility_llm() -> LMStudioClient:
    """Modelo pequeno e barato para tarefas curtas e estruturadas (classificar, extrair campos), que não
    respondem ao utilizador. Também aceita tool_choice forçado, ao contrário de alguns modelos de chat."""
    settings = get_settings()
    if settings.open_router_api_key:
        return LMStudioClient(
            base_url=settings.open_router_base_url,
            model=settings.guard_model,
            api_key=settings.open_router_api_key,
        )
    return get_lmstudio_client()


@lru_cache(maxsize=1)
def get_scope_guard() -> ScopeGuard:
    return ScopeGuard(get_utility_llm(), get_settings().knowledge_base_description)
