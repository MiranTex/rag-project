"""Área de pesquisa: projetos (documentos fixados, caderno de notas, matriz, comentários), pesquisas guardadas
e avaliações das respostas."""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Membros de um projeto além do dono: editor altera tudo menos os membros; viewer lê e comenta.
MemberRole = Literal["editor", "viewer"]
# note: nota livre; excerpt: destaque de um documento; answer: resposta do chat guardada; draft: texto gerado
# (esqueleto, estado da arte) para continuar a trabalhar.
ItemKind = Literal["note", "excerpt", "answer", "draft"]
CitationStyle = Literal["apa", "iso690", "bibtex"]


class Project(BaseModel):
    project_id: str
    owner_id: str
    title: str
    # Pergunta de investigação: orienta o chat do projeto, o esqueleto e o estado da arte.
    question: str = ""
    description: str = ""
    # Tipo de trabalho a escrever (chave de document_types.json), para o esqueleto.
    work_type: str = ""
    created_at: str
    updated_at: str


class ProjectMember(BaseModel):
    project_id: str
    user_id: str
    role: MemberRole


class ProjectDocument(BaseModel):
    project_id: str
    document_id: str
    added_by: str
    added_at: str


class NotebookItem(BaseModel):
    item_id: str
    project_id: str
    kind: ItemKind
    title: str = ""
    text: str = ""
    # De onde veio: {document_id, filename, page} num destaque; {question, sources} numa resposta.
    source: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_by: str
    created_at: str
    updated_at: str


class Comment(BaseModel):
    comment_id: str
    project_id: str
    # Comentário a uma entrada do caderno; None: comentário ao projeto.
    item_id: str | None = None
    author_id: str
    text: str
    created_at: str


class SavedSearch(BaseModel):
    search_id: str
    owner_id: str
    name: str
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    # Documentos carregados depois disto contam como novos para esta pesquisa.
    last_seen_at: str


class AnswerFeedback(BaseModel):
    feedback_id: str
    user_id: str
    rating: Literal[-1, 1]
    reason: str = ""
    question: str
    answer: str
    mode: str = "agent"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    project_id: str | None = None
    created_at: str


# ---- Pedidos e respostas da API ----


class ResearchFilters(BaseModel):
    document_type: str | None = None
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    fields: dict[str, str] = Field(default_factory=dict)
    sections: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question: str = ""
    description: str = ""
    work_type: str = ""


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    question: str | None = None
    description: str | None = None
    work_type: str | None = None


class MemberInfo(BaseModel):
    user_id: str
    username: str
    display_name: str = ""
    role: Literal["owner", "editor", "viewer"]


class MemberAdd(BaseModel):
    username: str
    role: MemberRole = "viewer"


class DocumentCard(BaseModel):
    """Resumo de um documento indexado para a área de pesquisa (quem só usa o chat também o vê)."""

    document_id: str
    filename: str
    title: str = ""
    year: int | None = None
    document_type: str = ""
    authors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    abstract: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    page_count: int = 0


class ProjectSummary(BaseModel):
    project: Project
    my_role: Literal["owner", "editor", "viewer"]
    document_count: int
    item_count: int


class ProjectDetail(BaseModel):
    project: Project
    my_role: Literal["owner", "editor", "viewer"]
    members: list[MemberInfo]
    documents: list[DocumentCard]


class ItemCreate(BaseModel):
    kind: ItemKind = "note"
    title: str = ""
    text: str = ""
    source: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    title: str | None = None
    text: str | None = None
    tags: list[str] | None = None


class ItemView(NotebookItem):
    author: str = ""
    comment_count: int = 0


class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    item_id: str | None = None


class CommentView(Comment):
    author: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    filters: ResearchFilters = Field(default_factory=ResearchFilters)
    top_k: int = Field(default=12, ge=1, le=30)
    project_id: str | None = None


class SearchHit(BaseModel):
    document_id: str
    filename: str
    title: str = ""
    year: int | None = None
    document_type: str = ""
    page: int
    section: str | None = None
    text: str
    score: float


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=2)
    filters: ResearchFilters = Field(default_factory=ResearchFilters)


class SavedSearchView(SavedSearch):
    new_count: int = 0


class TopicRequest(BaseModel):
    topic: str = Field(min_length=3)
    filters: ResearchFilters = Field(default_factory=ResearchFilters)
    max_documents: int = Field(default=15, ge=3, le=40)
    project_id: str | None = None


class ClaimCheckRequest(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    project_id: str | None = None


class SkeletonRequest(BaseModel):
    topic: str = Field(min_length=3)
    work_type: str = ""
    project_id: str | None = None


class StateOfArtRequest(BaseModel):
    topic: str = ""
    max_documents: int = Field(default=8, ge=1, le=15)


class MatrixFillRequest(BaseModel):
    dimensions: list[str] = Field(min_length=1, max_length=6)


class MatrixUpdate(BaseModel):
    dimensions: list[str] = Field(max_length=6)
    # {document_id: {dimensão: resumo escrito pela pessoa}}
    notes: dict[str, dict[str, str]] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1)
    format: Literal["docx", "md"] = "docx"


class FeedbackCreate(BaseModel):
    rating: Literal[-1, 1]
    reason: str = ""
    question: str
    answer: str
    mode: str = "agent"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    project_id: str | None = None
