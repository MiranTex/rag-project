from collections import defaultdict

from pydantic import BaseModel, Field

from backend.agent.tools.base import SourceRef, ToolContext, ToolError, ToolResult, tool

MAX_READ_CHARS = 20_000


class ListDocumentsParams(BaseModel):
    pass


@tool(
    name="list_documents",
    description="Lista os documentos indexados (id, nome do ficheiro, número de chunks).",
    params=ListDocumentsParams,
)
def list_documents(params: ListDocumentsParams, ctx: ToolContext) -> ToolResult:
    # Documentos à espera de revisão ainda não estão no índice.
    docs = [d for d in ctx.registry.list_documents() if d.status == "indexed"]
    content = [
        {"document_id": d.document_id, "filename": d.filename, "chunk_count": d.chunk_count}
        for d in docs
    ]
    return ToolResult(content=content, summary=f"{len(docs)} documento(s) indexado(s)")


class SearchDocumentsParams(BaseModel):
    query: str = Field(description="O que procurar, em linguagem natural ou palavras-chave.")
    document_id: str | None = Field(
        default=None,
        description="Restringe a pesquisa a um documento. Omitir para pesquisar em todos.",
    )
    top_k: int | None = Field(default=None, ge=1, le=12, description="Número de trechos a devolver.")


@tool(
    name="search_documents",
    description=(
        "Pesquisa híbrida (semântica + palavras-chave) nos documentos indexados. "
        "Devolve os trechos mais relevantes com ficheiro e página. "
        "Pode ser chamada várias vezes com termos diferentes."
    ),
    params=SearchDocumentsParams,
)
def search_documents(params: SearchDocumentsParams, ctx: ToolContext) -> ToolResult:
    sources = ctx.pipeline.retrieve_sources(
        question=params.query,
        top_k=params.top_k or ctx.top_k,
        document_id=params.document_id or ctx.default_document_id,
    )
    content = [
        {
            "document_id": s.document_id,
            "filename": s.filename,
            "page": s.page,
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
        "Lê o texto completo de um documento, página a página (opcionalmente só um intervalo de páginas). "
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
        raise ToolError("Sem texto no intervalo de páginas pedido.")

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
