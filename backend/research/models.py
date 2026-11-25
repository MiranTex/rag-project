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


class ProjectSection(BaseModel):
    """Uma parte do projeto (ex.: "Requisitos funcionais", "Riscos", "Capítulo 2"). O código não conhece nenhum
    assunto: as secções são dados de cada projeto, propostos pelo LLM a partir da conversa ou escritos à mão."""

    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectStructure(BaseModel):
    sections: list[ProjectSection] = Field(default_factory=list, max_length=30)
    # Estados possíveis de uma entrada (ex.: proposto, aprovado). Vazio: as entradas não têm estado.
    statuses: list[str] = Field(default_factory=list, max_length=12)


class Project(BaseModel):
    project_id: str
    owner_id: str
    title: str
    # Pergunta de investigação: orienta o chat do projeto, o esqueleto e o estado da arte.
    question: str = ""
    description: str = ""
    # Tipo de trabalho a escrever (chave de document_types.json), para o esqueleto.
    work_type: str = ""
    # Secções e estados definidos pelo próprio projeto (ver ProjectStructure).
    structure: ProjectStructure = Field(default_factory=ProjectStructure)
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
    # De onde veio: {document_id, filename, page} num destaque; {question, sources} numa resposta. Numa proposta
    # do agente aceite, basis diz se o conteúdo vem dos documentos, do assistente ou dos dois.
    source: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    # Campos genéricos: a secção do projeto (key de ProjectSection), uma referência curta escolhida pelo projeto
    # (RF-001, Art. 3, Q-7…), um dos estados do projeto e atributos livres (prioridade, responsável…).
    section: str = ""
    ref: str = ""
    status: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: str
    updated_at: str


class ProjectConversation(BaseModel):
    """Conversa do chat guardada no projeto, visível aos membros. As mensagens são as da interface (pergunta,
    resposta, fontes, passos do agente, propostas e a decisão sobre cada uma)."""

    conversation_id: str
    project_id: str
    title: str
    created_by: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ProjectInvitation(BaseModel):
    """Convite por email para um projeto. Guarda-se só o hash do token; o link é mostrado uma vez a quem convida."""

    invitation_id: str
    project_id: str
    email: str
    role: MemberRole
    token_hash: str
    invited_by: str
    created_at: str
    expires_at: str
    accepted_by: str | None = None
    accepted_at: str | None = None


class Comment(BaseModel):
    comment_id: str
    project_id: str
    # Comentário a uma entrada do caderno; None: comentário ao projeto.
    item_id: str | None = None
    author_id: str
    text: str
    created_at: str
    # Escrito por um agente externo (MCP) em nome do autor: o nome do token. Vazio se veio da interface.
    via: str = ""


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
    structure: ProjectStructure = Field(default_factory=ProjectStructure)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    question: str | None = None
    description: str | None = None
    work_type: str | None = None
    structure: ProjectStructure | None = None


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
    section: str = ""
    ref: str = Field(default="", max_length=64)
    status: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)


class ItemUpdate(BaseModel):
    title: str | None = None
    text: str | None = None
    tags: list[str] | None = None
    section: str | None = None
    ref: str | None = Field(default=None, max_length=64)
    status: str | None = None
    fields: dict[str, Any] | None = None
    # Origem do conteúdo novo (proposta do agente aceite): documents, assistant ou mixed; fica em source.basis.
    basis: Literal["documents", "assistant", "mixed"] | None = None
    # Proposta de um agente externo (MCP) aceite: o nome do token; fica em source.via.
    via: str | None = Field(default=None, max_length=120)


# ---- Projeto a partir de uma conversa do chat ----


class ConversationSource(BaseModel):
    document_id: str = ""
    filename: str = ""
    page: int | None = None
    text: str = ""


class ConversationTurn(BaseModel):
    question: str = ""
    answer: str = ""
    sources: list[ConversationSource] = Field(default_factory=list)


class ConversationDraftRequest(BaseModel):
    turns: list[ConversationTurn] = Field(min_length=1, max_length=60)
    # Indicação opcional da pessoa sobre o que quer do projeto ("especificação para um software", "parecer"…).
    goal: str = Field(default="", max_length=1000)


class DraftItem(BaseModel):
    section: str = ""
    ref: str = Field(default="", max_length=64)
    title: str = ""
    text: str = ""
    status: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    # Páginas dos documentos em que a entrada se apoia: [{document_id, filename, page}].
    sources: list[dict[str, Any]] = Field(default_factory=list)


class ProjectDraft(BaseModel):
    """Proposta de projeto para a pessoa rever antes de criar; `generated` é False quando o LLM não respondeu e
    a proposta é só a conversa arrumada numa secção."""

    title: str
    description: str = ""
    question: str = ""
    structure: ProjectStructure = Field(default_factory=ProjectStructure)
    items: list[DraftItem] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    generated: bool = True


class ProjectFromDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    question: str = ""
    structure: ProjectStructure = Field(default_factory=ProjectStructure)
    items: list[DraftItem] = Field(default_factory=list, max_length=300)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    # A conversa original fica no caderno como respostas guardadas (com as fontes).
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=60)
    members: list[MemberAdd] = Field(default_factory=list, max_length=50)


class ProjectFromDraftResult(BaseModel):
    detail: ProjectDetail
    # O que não foi possível fazer (utilizador desconhecido, documento já não indexado…), para mostrar à pessoa.
    warnings: list[str] = Field(default_factory=list)


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


class ConversationSummary(BaseModel):
    conversation_id: str
    project_id: str
    title: str
    created_by: str
    author: str = ""
    message_count: int = 0
    pending_proposals: int = 0
    created_at: str
    updated_at: str


class ConversationView(ConversationSummary):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    can_edit: bool = False


class ConversationSave(BaseModel):
    title: str = Field(default="", max_length=200)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=200)


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: MemberRole = "viewer"


class InvitationView(BaseModel):
    invitation_id: str
    email: str
    role: MemberRole
    invited_by: str = ""
    created_at: str
    expires_at: str


class InvitationCreated(InvitationView):
    # Só nesta resposta: quem convida copia o link e envia-o.
    token: str


class InvitationInfo(BaseModel):
    """O que a página pública do convite mostra (sem login)."""

    project_title: str
    invited_by: str
    email: str
    role: MemberRole
    status: Literal["pending", "accepted", "expired"]
    signup_allowed: bool


class InvitationSignup(BaseModel):
    username: str = Field(min_length=2, max_length=255)
    display_name: str = Field(default="", max_length=255)
    password: str = Field(min_length=8)
