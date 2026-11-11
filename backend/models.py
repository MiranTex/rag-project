from typing import Any, Literal

from pydantic import BaseModel, Field


# extracting/indexing: há um trabalho em background (ver JobQueue); failed: a extração falhou (ver error).
DocumentStatus = Literal["extracting", "pending_review", "indexing", "indexed", "failed"]
# original: nome do ficheiro carregado; suggested: gerado da ficha no upload; manual: escolhido à mão.
NameSource = Literal["original", "suggested", "manual"]


class DocumentInfo(BaseModel):
    document_id: str
    # Nome no sistema: o que aparece na lista, nas fontes e nas citações (ver document_naming.py).
    filename: str
    original_filename: str = ""
    # Nome do PDF em disco, dentro de UPLOAD_DIR. Vazio nos documentos antigos, guardados com o nome original.
    storage_name: str = ""
    name_source: NameSource = "original"
    sha256: str
    created_at: str
    chunk_count: int
    # Documentos registados antes da fase de revisão já estavam indexados.
    status: DocumentStatus = "indexed"
    page_count: int = 0
    alert_count: int = 0
    # Resumo da ficha (ver DocumentMetadata) para a listagem; a ficha completa fica com a extração.
    title: str = ""
    year: int | None = None
    document_type: str = ""
    # Último erro de um trabalho em background (vazio quando correu bem).
    error: str = ""
    # Quem pôs a versão atual em revisão (upload ou extrair de novo) e quem aprovou a última versão indexada
    # (ids de utilizador; vazios nos documentos anteriores à autenticação e na aprovação automática).
    uploaded_by: str = ""
    approved_by: str = ""
    # Impressão digital do texto aprovado: extrair de novo e obter o mesmo texto não obriga a nova aprovação.
    approved_fingerprint: str = ""


class UploadResponse(BaseModel):
    message: str
    document: DocumentInfo


class PageAlert(BaseModel):
    code: str
    message: str


class ReviewPage(BaseModel):
    page: int
    text: str
    source: Literal["text", "ocr", "manual", "none"]
    ocr_confidence: float | None = None
    alerts: list[PageAlert] = Field(default_factory=list)
    excluded: bool = False
    edited: bool = False


FieldValue = str | list[str]


class DocumentMetadata(BaseModel):
    """Ficha de um documento: núcleo comum a todos os tipos + campos próprios do tipo (ver document_types.json).
    Proposta na extração (regras + LLM) e confirmada na revisão."""

    document_type: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1900, le=2100)
    keywords: list[str] = Field(default_factory=list)
    abstract: str = ""
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    # Só gravadas na aprovação, a partir do texto revisto (ver GET /extraction para a versão atual).
    references: list[str] = Field(default_factory=list)
    auto_filled: bool = False


class MetadataUpdate(BaseModel):
    document_type: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1900, le=2100)
    keywords: list[str] = Field(default_factory=list)
    abstract: str = ""
    fields: dict[str, FieldValue] = Field(default_factory=dict)


class DocumentTypeField(BaseModel):
    key: str
    label: str
    type: Literal["text", "list", "people"]
    hint: str = ""
    filterable: bool = False


class DocumentTypeInfo(BaseModel):
    key: str
    label: str
    description: str
    fields: list[DocumentTypeField]
    sections: list[dict[str, str]]


class SectionHeading(BaseModel):
    section: str
    label: str
    page: int
    text: str


class DocumentExtraction(BaseModel):
    document: DocumentInfo
    pages: list[ReviewPage]
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    sections: list[SectionHeading] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    suggested_name: str = ""


class RenameRequest(BaseModel):
    # None (ou vazio) volta ao nome sugerido pela ficha.
    name: str | None = None


class PageUpdateRequest(BaseModel):
    text: str | None = None
    excluded: bool | None = None


class PageOcrRequest(BaseModel):
    dpi: int | None = Field(default=None, ge=72, le=600)


class AskRequest(BaseModel):
    question: str = Field(min_length=2)
    document_id: str | None = None
    top_k: int | None = None
    include_debug: bool = False
    multi_query: bool = False
    multi_query_n: int = Field(default=3, ge=1, le=6)
    retrieval_mode: Literal["hybrid", "vector", "keyword"] | None = None
    keyword_top_k: int | None = Field(default=None, ge=1, le=50)
    # Projeto de pesquisa: a pergunta fica limitada aos documentos fixados nele.
    project_id: str | None = None
    session_id: str | None = None


class SourceChunk(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_index: int
    score: float
    text: str
    document_chunk_count: int | None = None
    lexical_score: float = 0.0
    section: str | None = None


class RetrievalDiagnostic(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_index: int
    document_chunk_count: int | None = None
    vector_score: float
    lexical_score: float
    keyword_overlap: float
    position_penalty: float
    density_score: float
    recency_boost: float
    final_score: float
    text_preview: str
    retrieval_mode: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    retrieval_diagnostics: list[RetrievalDiagnostic] | None = None
    expanded_queries: list[str] | None = None


class AgentTurn(BaseModel):
    question: str
    answer: str


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=2)
    profile: str | None = None
    document_id: str | None = None
    project_id: str | None = None
    history: list[AgentTurn] = Field(default_factory=list, max_length=20)


class AgentProfileInfo(BaseModel):
    name: str
    label: str
    description: str
    tools: list[str]


class ExportInfo(BaseModel):
    name: str
    size: int
    created_at: str


class User(BaseModel):
    user_id: str
    username: str
    display_name: str = ""
    # Papéis (ver backend/auth/permissions.py); as permissões são a união das de cada papel.
    roles: list[str] = Field(default_factory=list)
    active: bool = True
    # Identificador no sistema externo (claim "sub"); None nos utilizadores locais.
    external_id: str | None = None
    created_at: str


class CurrentUserInfo(BaseModel):
    user: User
    permissions: list[str]


class AuthConfig(BaseModel):
    mode: Literal["local", "external"]
    # Login externo com os papéis vindos do token: não se editam nesta aplicação.
    roles_from_token: bool = False


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUserInfo


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8)
    display_name: str = ""
    roles: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str | None = None
    roles: list[str] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class SettingInfo(BaseModel):
    key: str
    label: str
    help: str
    group: str
    kind: str
    choices: list[str] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    value: Any
    # Valor do .env; overridden: alterado na aplicação (por cima do .env).
    default: Any
    overridden: bool


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


JobStatus = Literal["queued", "running", "done", "failed"]


class Job(BaseModel):
    id: int
    kind: str
    document_id: str
    status: JobStatus
    payload: dict = Field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    worker_id: str = ""
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
