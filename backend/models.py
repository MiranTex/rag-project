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


class SourceChunk(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_index: int
    score: float
    text: str
    document_chunk_count: int | None = None


class RetrievalDiagnostic(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_index: int
    document_chunk_count: int | None = None
    vector_score: float
    keyword_overlap: float
    position_penalty: float
    density_score: float
    recency_boost: float
    final_score: float
    text_preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    retrieval_diagnostics: list[RetrievalDiagnostic] | None = None
