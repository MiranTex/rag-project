import copy
import logging
from functools import lru_cache

from sqlalchemy import Engine

from backend.agent.guard import ScopeGuard
from backend.auth.authenticators import Authenticator, build_authenticator
from backend.agent.tools import ToolRegistry, build_registry
from backend.config import get_env_settings, get_settings, install_settings_source, on_settings_change
from backend.repositories.contracts import (
    AccessTokenRepository,
    DocumentRepository,
    ExtractionRepository,
    FeedbackRepository,
    JobQueue,
    LLMCredentialsRepository,
    LLMSettingsRepository,
    ResearchRepository,
    SettingsRepository,
    UserRepository,
)
from backend.repositories.research_sql import SqlFeedbackRepository, SqlResearchRepository
from backend.repositories.database import upgrade_database
from backend.repositories.legacy_import import import_legacy_json
from backend.repositories.sql import (
    SqlAccessTokenRepository,
    SqlDocumentRepository,
    SqlExtractionRepository,
    SqlJobQueue,
    SqlLLMCredentialsRepository,
    SqlLLMSettingsRepository,
    SqlSettingsRepository,
    SqlUserRepository,
    create_db_engine,
)
from backend.services.document_profiles import upsert_profile
from backend.services.document_renamer import DocumentRenamer
from backend.services.document_types import DocumentTypes, load_document_types
from backend.services.export_store import ExportStore
from backend.services.keyword_index import KeywordIndex
from backend.models import LLMProviderConfig
from backend.services.llm_providers import ConfigurableLLM, LLMChoice, Role, choose_llm, env_fallback
from backend.services.memory import SessionMemory
from backend.services.object_storage import storage_for
from backend.services.rag_pipeline import RagPipeline
from backend.services.secret_box import SecretBox
from backend.services.vector_store import VectorStore


@lru_cache(maxsize=1)
def get_database() -> Engine:
    """Engine da base de dados, com o esquema atualizado e os dados JSON antigos importados (uma vez)."""
    url = get_env_settings().database_url
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
def get_users() -> UserRepository:
    return SqlUserRepository(get_database())


@lru_cache(maxsize=1)
def get_access_tokens() -> AccessTokenRepository:
    return SqlAccessTokenRepository(get_database())


@lru_cache(maxsize=1)
def get_research_repository() -> ResearchRepository:
    return SqlResearchRepository(get_database())


@lru_cache(maxsize=1)
def get_feedback_repository() -> FeedbackRepository:
    return SqlFeedbackRepository(get_database())


@lru_cache(maxsize=1)
def get_settings_repository() -> SettingsRepository:
    return SqlSettingsRepository(get_database())


def install_settings_overrides() -> None:
    """Liga as configurações alteradas na aplicação (base de dados) a get_settings(). Corre no arranque da API
    e do worker; sem isto (por exemplo nos testes) valem só as do .env."""
    install_settings_source(lambda: get_settings_repository().load())


@lru_cache(maxsize=1)
def get_authenticator() -> Authenticator:
    return build_authenticator(get_settings(), get_users())


@lru_cache(maxsize=1)
def get_document_types() -> DocumentTypes:
    return load_document_types(get_settings().document_types_file)


@lru_cache(maxsize=1)
def get_extraction_store() -> ExtractionRepository:
    return SqlExtractionRepository(get_database())


def build_vector_store(collection_name: str) -> VectorStore:
    """Vetores no PostgreSQL da DATABASE_URL (pgvector); as coleções são linhas da tabela vector_embeddings."""
    if not get_settings().uses_postgres():
        raise RuntimeError("Os vetores ficam no PostgreSQL (pgvector): DATABASE_URL tem de ser PostgreSQL")
    return VectorStore(get_database(), collection_name)


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return build_vector_store(get_settings().vector_collection)


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
    store = build_vector_store(f"{settings.vector_collection}_profiles")
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
def get_llm_settings() -> LLMSettingsRepository:
    return SqlLLMSettingsRepository(get_database())


def active_llm_config() -> LLMProviderConfig:
    """Fornecedor de LLM escolhido na aplicação (Configurações → Modelo de linguagem); sem nenhum, o do .env."""
    return get_llm_settings().get_active() or env_fallback(get_settings())


@lru_cache(maxsize=1)
def get_secret_box() -> SecretBox:
    return SecretBox(get_env_settings().credentials_secret_key)


@lru_cache(maxsize=1)
def get_llm_credentials() -> LLMCredentialsRepository:
    return SqlLLMCredentialsRepository(get_database(), get_secret_box())


def resolve_llm(user_id: str | None, project_id: str | None = None) -> LLMChoice:
    """Fornecedor e chave de um pedido: do projeto, da pessoa ou da plataforma (ver choose_llm).

    project_id só depois de confirmar que a pessoa é membro do projeto (load_project / project_scope): aqui não
    se volta a verificar, e a chave do projeto não pode servir quem não pertence a ele."""
    if not get_secret_box().available:
        return LLMChoice(active_llm_config(), "platform")
    credentials = get_llm_credentials()
    project = credentials.get("project", project_id) if project_id else None
    user = credentials.get("user", user_id) if user_id else None
    return choose_llm(project, user, active_llm_config)


def llm_for(user_id: str | None, project_id: str | None = None, role: Role = "chat") -> ConfigurableLLM:
    """Cliente de LLM para um pedido, com a chave que lhe cabe (escolhida uma vez, ao criar o cliente)."""
    choice = resolve_llm(user_id, project_id)
    return ConfigurableLLM(lambda: choice.config, role=role)


def pipeline_for(user_id: str | None, project_id: str | None = None) -> RagPipeline:
    """O pipeline partilhado (índices, memória), mas a responder com a chave deste pedido."""
    pipeline = copy.copy(get_rag_pipeline())
    pipeline.lmstudio_client = llm_for(user_id, project_id)
    return pipeline


def scope_guard_for(user_id: str | None, project_id: str | None = None) -> ScopeGuard:
    return ScopeGuard(llm_for(user_id, project_id, "utility"), get_settings().knowledge_base_description)


@lru_cache(maxsize=1)
def get_lmstudio_client() -> ConfigurableLLM:
    """Sempre com a chave da plataforma (estado de saúde, avaliação). Pedidos de pessoas: llm_for."""
    return ConfigurableLLM(active_llm_config, role="chat")


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
        # Memória das conversas em uploads/memory/ (no disco local ou no storage S3).
        memory_service=SessionMemory(storage=storage_for(settings, "uploads"), prefix="memory"),
    )


@lru_cache(maxsize=1)
def get_export_store() -> ExportStore:
    return ExportStore(storage_for(get_settings(), "exports"))


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    return build_registry()


@lru_cache(maxsize=1)
def get_utility_llm() -> ConfigurableLLM:
    """Modelo pequeno e barato para tarefas curtas e estruturadas (classificar, extrair campos), que não
    respondem ao utilizador. Também aceita tool_choice forçado, ao contrário de alguns modelos de chat.
    Sem modelo utilitário configurado, usa o modelo de chat. Sempre com a chave da plataforma: serve a ficha dos
    documentos, que são da base toda e não de uma pessoa ou projeto. Pedidos de pessoas: llm_for."""
    return ConfigurableLLM(active_llm_config, role="utility")


# Serviços que guardam valores das configurações quando são criados: recriam-se quando estas mudam.
for _cached in (get_rag_pipeline, get_renamer):
    on_settings_change(_cached.cache_clear)
