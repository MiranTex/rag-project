import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine

from backend.agent.guard import ScopeGuard
from backend.agent.tools import ToolRegistry, build_registry
from backend.config import get_settings
from backend.repositories.contracts import DocumentRepository, ExtractionRepository, JobQueue
from backend.repositories.database import upgrade_database
from backend.repositories.legacy_import import import_legacy_json
from backend.repositories.sql import SqlDocumentRepository, SqlExtractionRepository, SqlJobQueue, create_db_engine
from backend.services.document_profiles import upsert_profile
from backend.services.document_renamer import DocumentRenamer
from backend.services.document_types import DocumentTypes, load_document_types
from backend.services.export_store import ExportStore
from backend.services.keyword_index import KeywordIndex
from backend.services.lmstudio_client import LMStudioClient
from backend.services.memory import SessionMemory
from backend.services.rag_pipeline import RagPipeline
from backend.services.vector_store import VectorStore


@lru_cache(maxsize=1)
def get_database() -> Engine:
    """Engine da base de dados, com o esquema atualizado e os dados JSON antigos importados (uma vez)."""
    url = get_settings().database_url
    upgrade_database(url)
    engine = create_db_engine(url)
    import_legacy_json(SqlDocumentRepository(engine), SqlExtractionRepository(engine))
    return engine


@lru_cache(maxsize=1)
def get_registry() -> DocumentRepository:
    return SqlDocumentRepository(get_database())


@lru_cache(maxsize=1)
def get_job_queue() -> JobQueue:
    return SqlJobQueue(get_database())


@lru_cache(maxsize=1)
def get_document_types() -> DocumentTypes:
    return load_document_types(get_settings().document_types_file)


@lru_cache(maxsize=1)
def get_extraction_store() -> ExtractionRepository:
    return SqlExtractionRepository(get_database())


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.chroma_collection,
    )


# Secções que não descrevem o assunto do documento (para o vetor de um documento sem resumo).
NON_CONTENT_SECTIONS = {"front_matter", "references", "appendix"}

logger = logging.getLogger(__name__)


def document_body(chunks: list[dict]) -> str:
    ordered = sorted(chunks, key=lambda c: c["metadata"].get("chunk_index", 0))
    return " ".join(c["text"] for c in ordered if c["metadata"].get("section") not in NON_CONTENT_SECTIONS)


@lru_cache(maxsize=1)
def get_profile_store() -> VectorStore:
    """Índice de documentos (um vetor por documento). Na primeira utilização cria os vetores que faltam
    para documentos indexados antes de este índice existir."""
    settings = get_settings()
    store = VectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=f"{settings.chroma_collection}_profiles",
    )
    try:
        existing = store.list_ids()
        for info in get_registry().list_documents():
            if info.status != "indexed" or info.document_id in existing:
                continue
            metadata = get_extraction_store().load_metadata(info.document_id)
            body = document_body(get_vector_store().list_chunks(info.document_id))
            upsert_profile(store, settings.embedding_model, info, metadata, get_document_types().get(metadata.document_type), body)
            logger.info("Índice de documentos: vetor criado para %s", info.filename)
    except Exception:
        logger.warning("Não foi possível completar o índice de documentos", exc_info=True)
    return store


@lru_cache(maxsize=1)
def get_renamer() -> DocumentRenamer:
    return DocumentRenamer(
        registry=get_registry(),
        vector_store=get_vector_store(),
        keyword_index=get_keyword_index(),
        profile_store=get_profile_store(),
        document_types=get_document_types(),
        auto_rename=get_settings().auto_rename_documents,
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
        max_tokens=settings.lm_studio_max_tokens,
    )


@lru_cache(maxsize=1)
def get_rag_pipeline() -> RagPipeline:
    settings = get_settings()
    memory_dir = Path(settings.upload_dir) / "memory"
    return RagPipeline(
        embedding_model=settings.embedding_model,
        vector_store=get_vector_store(),
        keyword_index=get_keyword_index(),
        lmstudio_client=get_lmstudio_client(),
        rerank_weights=settings.parse_rerank_weights("default"),
        retrieval_mode_default=settings.retrieval_mode_default,
        keyword_candidate_multiplier=settings.keyword_candidate_multiplier,
        memory_service=SessionMemory(storage_dir=memory_dir),
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
