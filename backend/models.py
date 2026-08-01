from typing import Literal

from pydantic import BaseModel, Field


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    sha256: str
    created_at: str
    chunk_count: int


class UploadResponse(BaseModel):
    message: str
    document: DocumentInfo


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
