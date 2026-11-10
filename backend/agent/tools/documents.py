from collections import defaultdict

from pydantic import BaseModel, Field

from backend.agent.tools.base import SourceRef, ToolContext, ToolError, ToolResult, tool
from backend.services.document_types import BUILTIN_LABELS, section_label
from backend.services.embeddings import embed_query
from backend.services.search_filters import SearchFilters

MAX_READ_CHARS = 20_000


def _metadata(ctx: ToolContext, document_id: str):
    return ctx.extraction_store.load_metadata(document_id) if ctx.extraction_store else None


def _filter_fields(ctx: ToolContext) -> set[str]:
    if not ctx.document_types:
        return set()
    return {f.key for t in ctx.document_types.types.values() for f in t.fields if f.filterable}


def _section_keys(ctx: ToolContext) -> set[str]:
    keys = set(BUILTIN_LABELS)
    if ctx.document_types:
        keys |= {sec.key for t in ctx.document_types.types.values() for sec in t.sections}
    return keys


class FilterParams(BaseModel):
    document_type: str | None = Field(default=None, description="Só documentos deste tipo (chave, ver list_documents).")
    year_from: int | None = Field(default=None, ge=1900, le=2100, description="Só documentos deste ano em diante.")
    year_to: int | None = Field(default=None, ge=1900, le=2100, description="Só documentos até este ano.")
    fields: dict[str, str] = Field(
        default_factory=dict,
        description="Campos filtráveis da ficha, valor exato como aparece em list_documents (ex.: {\"department\": \"...\"}).",
    )


def _build_filters(ctx: ToolContext, params: FilterParams, sections: list[str] | None = None, document_id: str | None = None) -> SearchFilters:
    """Valida as chaves contra os tipos configurados: um erro com as opções válidas deixa o modelo corrigir-se."""
    if params.document_type and ctx.document_types and params.document_type not in ctx.document_types.types:
        raise ToolError(f"Tipo desconhecido: {params.document_type}. Tipos: {sorted(ctx.document_types.types)}")
    unknown_fields = set(params.fields) - _filter_fields(ctx)
    if unknown_fields:
        raise ToolError(f"Campos não filtráveis: {sorted(unknown_fields)}. Filtráveis: {sorted(_filter_fields(ctx))}")
    unknown_sections = set(sections or []) - _section_keys(ctx)
    if unknown_sections:
        raise ToolError(f"Secções desconhecidas: {sorted(unknown_sections)}. Secções: {sorted(_section_keys(ctx))}")
    return SearchFilters(
        document_id=document_id,
        document_type=params.document_type,
        year_from=params.year_from,
        year_to=params.year_to,
        sections=list(sections or []),
        fields=dict(params.fields),
    )


class ListDocumentsParams(BaseModel):
    pass


@tool(
    name="list_documents",
    description=(
        "Lista os documentos indexados com a ficha resumida (tipo, título, ano, campos filtráveis) e os tipos de "
        "documento desta base, com as secções e os campos que se podem usar como filtros nas pesquisas."
    ),
    params=ListDocumentsParams,
)
def list_documents(params: ListDocumentsParams, ctx: ToolContext) -> ToolResult:
    # Documentos à espera de revisão ainda não estão no índice.
    docs = [d for d in ctx.registry.list_documents() if d.status == "indexed"]
    documents = []
    for d in docs:
        item = {"document_id": d.document_id, "filename": d.filename, "chunk_count": d.chunk_count}
        metadata = _metadata(ctx, d.document_id)
        if metadata:
            item.update(document_type=metadata.document_type, title=metadata.title, year=metadata.year)
            item.update({key: value for key, value in metadata.fields.items() if key in _filter_fields(ctx)})
        documents.append({key: value for key, value in item.items() if value not in (None, "", [])})

    content: dict = {"documents": documents}
    if ctx.document_types:
        content["document_types"] = {
            t.key: {
                "label": t.label,
                "sections": [sec.key for sec in t.sections] + sorted(BUILTIN_LABELS),
                "filter_fields": [f.key for f in t.fields if f.filterable],
            }
            for t in ctx.document_types.types.values()
        }
    return ToolResult(content=content, summary=f"{len(docs)} documento(s) indexado(s)")


class SearchDocumentsParams(FilterParams):
    query: str = Field(description="O que procurar, em linguagem natural ou palavras-chave.")
    document_id: str | None = Field(
        default=None,
        description="Restringe a pesquisa a um documento. Omitir para pesquisar em todos.",
    )
    sections: list[str] = Field(
        default_factory=list,
        description=(
            "Só excertos destas secções (chaves, ver list_documents), ex.: ['conclusion'] para conclusões, "
            "['methodology'] para métodos. Útil para comparar a mesma parte de vários documentos."
        ),
    )
    top_k: int | None = Field(default=None, ge=1, le=12, description="Número de trechos a devolver.")


@tool(
    name="search_documents",
    description=(
        "Pesquisa híbrida (semântica + palavras-chave) nos documentos indexados. "
        "Devolve os trechos mais relevantes com ficheiro, página e secção. "
        "Aceita filtros por tipo de documento, ano, secção e campos da ficha. "
        "Pode ser chamada várias vezes com termos diferentes."
    ),
    params=SearchDocumentsParams,
)
def search_documents(params: SearchDocumentsParams, ctx: ToolContext) -> ToolResult:
    filters = _build_filters(ctx, params, params.sections, params.document_id or ctx.default_document_id)
    sources = ctx.pipeline.retrieve_sources(question=params.query, top_k=params.top_k or ctx.top_k, filters=filters)
    content = [
        {
            "document_id": s.document_id,
            "filename": s.filename,
            "page": s.page,
            **({"section": s.section} if s.section else {}),
            "score": round(s.score, 3),
            "text": s.text,
        }
        for s in sources
    ]
    refs = [SourceRef(filename=s.filename, page=s.page, document_id=s.document_id) for s in sources]
    pages = sorted({f"{s.filename} p.{s.page}" for s in sources})
    return ToolResult(
        content=content,
        summary=f"{len(sources)} trecho(s): {', '.join(pages)}" if sources else "sem resultados",
        sources=refs,
    )


class ReadDocumentParams(BaseModel):
    document_id: str = Field(description="Id do documento (ver list_documents).")
    page_start: int | None = Field(default=None, ge=1, description="Primeira página a ler (inclusive).")
    page_end: int | None = Field(default=None, ge=1, description="Última página a ler (inclusive).")
    section: str | None = Field(
        default=None,
        description="Lê só esta secção (chave, ver get_document_overview), ex.: 'conclusion'.",
    )


def merge_chunk_texts(texts: list[str], min_overlap: int = 20) -> str:
    """Junta chunks consecutivos removendo o overlap que o chunking repete no início de cada um."""
    merged = ""
    for text in texts:
        if not merged:
            merged = text
            continue
        overlap = 0
        tail = merged.rstrip(".")
        for size in range(min(len(tail), len(text), 400), min_overlap - 1, -1):
            if tail.endswith(text[:size]):
                overlap = size
                break
        merged = f"{tail}{text[overlap:]}" if overlap else f"{merged} {text}"
    return merged


@tool(
    name="read_document",
    description=(
        "Lê o texto completo de um documento, página a página (opcionalmente só um intervalo de páginas ou uma secção). "
        "Usar para resumos, extração exaustiva de dados ou para confirmar o texto exato antes de responder."
    ),
    params=ReadDocumentParams,
)
def read_document(params: ReadDocumentParams, ctx: ToolContext) -> ToolResult:
    info = ctx.registry.find_by_id(params.document_id)
    if not info:
        raise ToolError(f"Documento não encontrado: {params.document_id}")

    by_page: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for chunk in ctx.vector_store.list_chunks(params.document_id):
        meta = chunk["metadata"]
        page = int(meta["page"])
        if params.page_start and page < params.page_start:
            continue
        if params.page_end and page > params.page_end:
            continue
        if params.section and meta.get("section") != params.section:
            continue
        by_page[page].append((int(meta["chunk_index"]), chunk["text"]))

    pages = []
    total_chars = 0
    truncated = False
    for page in sorted(by_page):
        text = merge_chunk_texts([t for _, t in sorted(by_page[page])])
        if total_chars + len(text) > MAX_READ_CHARS:
            truncated = True
            break
        pages.append({"page": page, "text": text})
        total_chars += len(text)

    if not pages:
        raise ToolError("Sem texto no intervalo de páginas ou na secção pedida.")

    content: dict = {"filename": info.filename, "pages": pages}
    if truncated:
        content["truncated"] = (
            f"Texto cortado após a página {pages[-1]['page']}. Ler o resto com page_start={pages[-1]['page'] + 1}."
        )
    page_numbers = [p["page"] for p in pages]
    return ToolResult(
        content=content,
        summary=f"{info.filename}: p.{page_numbers[0]}–{page_numbers[-1]}" + (" (cortado)" if truncated else ""),
        sources=[SourceRef(filename=info.filename, page=p, document_id=info.document_id) for p in page_numbers],
    )


class DocumentOverviewParams(BaseModel):
    document_id: str = Field(description="Id do documento (ver list_documents).")


@tool(
    name="get_document_overview",
    description=(
        "Ficha e estrutura de um documento: tipo, título, autores, ano, campos próprios do tipo, palavras-chave, "
        "resumo, secções com as páginas onde estão e número de referências. Usar para conhecer um documento "
        "antes de o ler, ou para comparar vários documentos sem os ler inteiros."
    ),
    params=DocumentOverviewParams,
)
def get_document_overview(params: DocumentOverviewParams, ctx: ToolContext) -> ToolResult:
    info = ctx.registry.find_by_id(params.document_id)
    if not info or info.status != "indexed":
        raise ToolError(f"Documento não encontrado ou ainda não indexado: {params.document_id}")
    metadata = _metadata(ctx, info.document_id)
    doc_type = ctx.document_types.get(metadata.document_type if metadata else None) if ctx.document_types else None

    # A estrutura vem dos excertos indexados: é a do texto aprovado.
    by_section: dict[str, dict] = {}
    for chunk in sorted(ctx.vector_store.list_chunks(info.document_id), key=lambda c: c["metadata"]["chunk_index"]):
        meta = chunk["metadata"]
        key = meta.get("section")
        if not key:
            continue
        entry = by_section.setdefault(key, {"section": key, "pages": [], "excerpts": 0})
        entry["pages"].append(int(meta["page"]))
        entry["excerpts"] += 1
    sections = [
        {
            "section": entry["section"],
            "label": section_label(doc_type, entry["section"]) if doc_type else entry["section"],
            "pages": f"{min(entry['pages'])}–{max(entry['pages'])}" if min(entry["pages"]) != max(entry["pages"]) else str(entry["pages"][0]),
            "excerpts": entry["excerpts"],
        }
        for entry in by_section.values()
    ]

    content: dict = {"document_id": info.document_id, "filename": info.filename, "sections": sections}
    if metadata:
        content.update(
            document_type=doc_type.label if doc_type else metadata.document_type,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            fields={(doc_type.field(k).label if doc_type and doc_type.field(k) else k): v for k, v in metadata.fields.items()},
            keywords=metadata.keywords,
            abstract=metadata.abstract,
            references=len(metadata.references),
        )
    content = {key: value for key, value in content.items() if value not in (None, "", [], {})}
    return ToolResult(
        content=content,
        summary=f"{metadata.title if metadata and metadata.title else info.filename}: {len(sections)} secção(ões)",
    )


class FindSimilarParams(FilterParams):
    query: str | None = Field(
        default=None,
        description="Tema ou descrição do que se procura (ex.: 'recomendação de livros em bibliotecas').",
    )
    document_id: str | None = Field(
        default=None,
        description="Em vez de query: encontra documentos parecidos com este documento.",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Número de documentos a devolver.")


@tool(
    name="find_similar_documents",
    description=(
        "Encontra DOCUMENTOS (não excertos) sobre um tema, ou parecidos com outro documento, comparando a ficha "
        "de cada um (título, palavras-chave, resumo). Usar para 'que documentos existem sobre X?' ou para "
        "levantar o que já foi feito num tema. Aceita os mesmos filtros de search_documents (exceto secções)."
    ),
    params=FindSimilarParams,
)
def find_similar_documents(params: FindSimilarParams, ctx: ToolContext) -> ToolResult:
    if ctx.profile_store is None:
        raise ToolError("O índice de documentos não está disponível.")
    if not params.query and not params.document_id:
        raise ToolError("Indica query (um tema) ou document_id (um documento de referência).")

    if params.document_id:
        embedding = ctx.profile_store.get_embeddings([params.document_id]).get(params.document_id)
        if embedding is None:
            raise ToolError(f"Documento sem ficha no índice de documentos: {params.document_id}")
    else:
        embedding = embed_query(ctx.embedding_model, params.query)

    filters = _build_filters(ctx, params)
    extra = 1 if params.document_id else 0
    results = ctx.profile_store.query(embedding, params.top_k + extra, where=filters.to_chroma_where())
    documents = []
    for item in results:
        meta = item["metadata"]
        if meta["document_id"] == params.document_id:
            continue
        documents.append(
            {
                "document_id": meta["document_id"],
                "filename": meta.get("filename"),
                "title": meta.get("title"),
                "document_type": meta.get("document_type"),
                "year": meta.get("year"),
                "similarity": round(float(item["score"]), 3),
                "profile": item["text"][:400],
            }
        )
    documents = documents[: params.top_k]
    names = ", ".join((d["title"] or d["filename"] or d["document_id"])[:40] for d in documents[:3])
    return ToolResult(
        content=documents,
        summary=f"{len(documents)} documento(s)" + (f": {names}" + ("…" if len(documents) > 3 else "") if documents else ""),
    )

