from functools import lru_cache
from pathlib import Path
import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_chat_model: str = "local-model"
    open_router_api_key: str = ""
    open_router_base_url: str = "https://openrouter.ai/api/v1"
    open_router_chat_model: str = "anthropic/claude-sonnet-5.5"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    chroma_host: str = "127.0.0.1"
    chroma_port: int = 8001
    chroma_collection: str = "rag_documents"

    top_k: int = 4
    retrieval_mode_default: str = "hybrid"
    keyword_search_enabled: bool = True
    keyword_candidate_multiplier: int = 2
    keyword_bm25_k1: float = 1.5
    keyword_bm25_b: float = 0.75
    chunk_size: int = 1000
    chunk_overlap: int = 150
    upload_dir: str = "data/uploads"
    # Base de dados (registo, extrações, fila de trabalhos): sqlite:///… ou postgresql+psycopg://…
    database_url: str = "sqlite:///backend/storage/rag.db"
    # Workers da fila de extração/indexação dentro da API; 0 se correrem noutro processo (python -m backend.worker).
    indexing_workers: int = 1
    job_poll_seconds: float = 1.0
    # Trabalhos "running" há mais do que isto voltam à fila (worker que morreu a meio).
    job_stale_minutes: int = 60
    export_dir: str = "data/exports"
    agent_max_steps: int = 8
    guard_enabled: bool = True
    guard_model: str = "anthropic/claude-haiku-5.5"
    ocr_enabled: bool = True
    ocr_languages: str = "por+eng"
    ocr_dpi: int = 300
    ocr_min_text_chars: int = 30
    ocr_min_confidence: float = 60.0
    ocr_max_workers: int = 4
    # Fase de revisão: com auto-aprovação, documentos sem alertas são indexados logo após a extração.
    auto_approve_clean_documents: bool = False
    review_max_garbled_ratio: float = 0.15
    # Ficha do documento (tipo, título, autores, ano...) proposta pelo LLM na extração.
    metadata_extraction_enabled: bool = True
    # Nome no sistema gerado da ficha no upload (padrão name_pattern em document_types.json).
    auto_rename_documents: bool = True
    # Tipos de documento desta base de conhecimento (campos da ficha e títulos de secção).
    document_types_file: str = "backend/document_types.json"
    # Uma frase sobre esta base de conhecimento, usada nos prompts (guarda, agente, extração da ficha).
    knowledge_base_description: str = "Base de conhecimento com os documentos da organização."
    # Aprovação a quatro olhos: quem pôs o documento em revisão (upload ou extrair de novo) não o pode aprovar.
    # Ligada, a auto-aprovação de documentos sem alertas fica desligada.
    require_separate_approver: bool = False

    # Autenticação. local: utilizadores e palavras-passe desta aplicação (standalone).
    # external: tokens JWT emitidos por outro sistema (SSO/OIDC); os utilizadores são criados no primeiro acesso.
    auth_mode: str = "local"
    # Chave dos tokens locais (HS256). Vazia: gerada no arranque (as sessões caem a cada reinício).
    auth_secret_key: str = ""
    auth_token_minutes: int = 480
    # Administrador criado no arranque quando ainda não há utilizadores (modo local).
    auth_bootstrap_admin_username: str = ""
    auth_bootstrap_admin_password: str = ""
    # Modo external: como validar o token (uma das três) e que claims usar.
    auth_external_jwks_url: str = ""
    auth_external_public_key: str = ""
    auth_external_secret: str = ""
    auth_external_algorithms: str = "RS256"
    auth_external_issuer: str = ""
    auth_external_audience: str = ""
    auth_external_username_claim: str = "preferred_username"
    auth_external_name_claim: str = "name"
    # Claim com os papéis/grupos (ex.: "groups"). Vazia: os papéis são geridos nesta aplicação.
    auth_external_roles_claim: str = ""
    # Correspondência grupo externo -> papel interno, em JSON (ex.: {"rag-gestores": "manager"}).
    auth_external_role_map: str = "{}"
    # Papéis de um utilizador externo novo quando os papéis não vêm do token.
    auth_external_default_roles: str = "chat"
    # Origens do frontend autorizadas (separadas por vírgulas); "*" para qualquer uma.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    rerank_weights_default: str ='{"vector": 0.45, "lexical": 0.20, "keyword": 0.20, "position": 0.10, "density": 0.05}'
    rerank_weights_grounding: str = '{"vector": 0.35, "lexical": 0.25, "keyword": 0.25, "position": 0.10, "density": 0.05}'

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def parse_rerank_weights(self, profile: str = "default") -> dict[str, float]:
        raw = self.rerank_weights_default if profile == "default" else self.rerank_weights_grounding
        parsed = json.loads(raw)
        return {
            "vector": float(parsed.get("vector", 0.60)),
            "lexical": float(parsed.get("lexical", 0.0)),
            "keyword": float(parsed.get("keyword", 0.25)),
            "position": float(parsed.get("position", 0.10)),
            "density": float(parsed.get("density", 0.05)),
        }

    @staticmethod
    def split_list(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.export_dir).mkdir(parents=True, exist_ok=True)
    return settings
