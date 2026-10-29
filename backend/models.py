from typing import Literal

from pydantic import BaseModel, Field


DocumentStatus = Literal["pending_review", "indexed"]


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
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


class DocumentMetadata(BaseModel):
    """Ficha de um trabalho académico. Proposta na extração (regras + LLM) e confirmada na revisão."""

    title: str = ""
    authors: list[str] = Field(default_factory=list)
    advisors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1900, le=2100)
    course: str = ""
    institution: str = ""
    keywords: list[str] = Field(default_factory=list)
    abstract: str = ""
    # Só gravadas na aprovação, a partir do texto revisto (ver GET /extraction para a versão atual).
    references: list[str] = Field(default_factory=list)
    auto_filled: bool = False


class MetadataUpdate(BaseModel):
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    advisors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1900, le=2100)
    course: str = ""
    institution: str = ""
    keywords: list[str] = Field(default_factory=list)
    abstract: str = ""


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


class SourceChunk(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_index: int
    score: float
    text: str
    document_chunk_count: int | None = None
    lexical_score: float = 0.0


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
