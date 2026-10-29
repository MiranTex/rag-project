"""Tools de análise sobre vários documentos: o que ficou em aberto e comparação por dimensões.

Devolvem excertos com página (sem chamar o LLM); é o agente que sintetiza e cita.
"""

from collections import defaultdict
from dataclasses import replace

from pydantic import BaseModel, Field

from backend.agent.tools.base import SourceRef, ToolContext, ToolError, ToolResult, tool
from backend.agent.tools.documents import FilterParams, _build_filters, _metadata, merge_chunk_texts
from backend.services.document_types import section_label
from backend.services.search_filters import SearchFilters

MAX_OPEN_CHARS_PER_DOCUMENT = 2000
MAX_CELL_CHARS = 450


def _page_range(pages: list[int]) -> str:
    low, high = min(pages), max(pages)
    return str(low) if low == high else f"{low}–{high}"


def _document_header(ctx: ToolContext, document_id: str) -> dict:
    info = ctx.registry.find_by_id(document_id)
    metadata = _metadata(ctx, document_id)
    header = {"document_id": document_id, "filename": info.filename if info else document_id}
    if metadata:
        header.update(title=metadata.title, year=metadata.year, document_type=metadata.document_type)
    return {key: value for key, value in header.items() if value not in (None, "")}


class OpenQuestionsParams(FilterParams):
    query: str | None = Field(
        default=None,
        description=(
            "Tema (opcional). Com tema, devolve os excertos em aberto mais relevantes para ele; sem tema, "
            "percorre os documentos que passam nos filtros, dos mais recentes para os mais antigos."
        ),
    )
    max_documents: int = Field(default=8, ge=1, le=20, description="Máximo de documentos a devolver.")


@tool(
    name="find_open_questions",
    description=(
        "Junta o que ficou em aberto em vários documentos: as secções de trabalho futuro, limitações, "
        "recomendações ou próximos passos (configuradas por tipo de documento). Usar para 'o que ficou por fazer "
        "em X?' ou para encontrar temas para um trabalho novo. Lista à parte os documentos sem essas secções, "
        "que podem ter o mesmo conteúdo nas conclusões."
    ),
    params=OpenQuestionsParams,
)
def find_open_questions(params: OpenQuestionsParams, ctx: ToolContext) -> ToolResult:
    if not ctx.document_types:
        raise ToolError("Os tipos de documento não estão disponíveis.")
    types = ctx.document_types.types
    if params.document_type and params.document_type in types and not types[params.document_type].open_sections:
        raise ToolError(f"O tipo {params.document_type} não tem secções de pontos em aberto configuradas.")
    open_by_type = {key: set(t.open_sections) for key, t in types.items()}
    sections = sorted(open_by_type.get(params.document_type, set()) if params.document_type else set().union(*open_by_type.values()))
    filters = _build_filters(ctx, params, sections)

    # Documentos que passam nos filtros da ficha (tipo, ano, campos); as secções filtram os excertos.
    document_filter = replace(filters, sections=[])
    candidates = []
    for info in ctx.registry.list_documents():
        if info.status != "indexed":
            continue
        metadata = _metadata(ctx, info.document_id)
        values = {"document_id": info.document_id}
        if metadata:
            values.update(document_type=metadata.document_type, year=metadata.year, **metadata.fields)
        if document_filter.is_empty() or document_filter.matches(values):
            candidates.append((metadata.year if metadata and metadata.year else 0, info))

    # (documento, secção) -> [(chunk_index, página, texto)]
    found: dict[str, dict[str, list[tuple[int, int, str]]]] = defaultdict(lambda: defaultdict(list))
    without: list[str] = []
    if params.query:
        sources = ctx.pipeline.retrieve_sources(question=params.query, top_k=max(12, params.max_documents * 2), filters=filters)
        for s in sources:
            if len(found) >= params.max_documents and s.document_id not in found:
                continue
            found[s.document_id][s.section or ""].append((s.chunk_index, s.page, s.text))
    else:
        for _, info in sorted(candidates, key=lambda item: item[0], reverse=True):
            chunks = [c for c in ctx.vector_store.list_chunks(info.document_id) if c["metadata"].get("section") in sections]
            if not chunks:
                without.append(info.filename)
                continue
            if len(found) < params.max_documents:
                for c in chunks:
                    meta = c["metadata"]
                    found[info.document_id][meta["section"]].append((int(meta["chunk_index"]), int(meta["page"]), c["text"]))

    documents, refs = [], []
    for document_id, by_section in found.items():
        entry = _document_header(ctx, document_id)
        doc_type = ctx.document_types.get(entry.get("document_type"))
        budget = MAX_OPEN_CHARS_PER_DOCUMENT
        entry["open"] = []
        for key, items in by_section.items():
            items.sort()
            text = merge_chunk_texts([t for _, _, t in items])[:budget]
            budget -= len(text)
            pages = [p for _, p, _ in items]
            entry["open"].append({"section": section_label(doc_type, key) if key else "", "pages": _page_range(pages), "text": text})
            refs.extend(SourceRef(filename=entry["filename"], page=p, document_id=document_id) for p in sorted(set(pages)))
            if budget <= 0:
                break
        documents.append(entry)

    content: dict = {"documents": documents}
    if without:
        content["documents_without_open_sections"] = without
    if not documents and not without:
        content["note"] = "Nenhum documento com estas secções passa nos filtros."
    summary = f"{len(documents)} documento(s) com pontos em aberto" + (f", {len(without)} sem essas secções" if without else "")
    return ToolResult(content=content, summary=summary, sources=refs)


class CompareDocumentsParams(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=8, description="Documentos a comparar (ver list_documents).")
    dimensions: list[str] = Field(
        min_length=1,
        max_length=6,
        description="Aspetos a comparar, em linguagem natural (ex.: 'método', 'dados usados', 'principais resultados').",
    )
    excerpts_per_cell: int = Field(default=2, ge=1, le=3, description="Excertos por documento e dimensão.")


@tool(
    name="compare_documents",
    description=(
        "Compara vários documentos lado a lado: para cada documento e cada dimensão pedida devolve os excertos "
        "mais relevantes com página, mais a ficha de cada um. Usar para tabelas de comparação ou revisões de "
        "literatura; resume cada célula e cita as páginas. Para entregar a tabela em ficheiro, usar export_csv."
    ),
    params=CompareDocumentsParams,
)
def compare_documents(params: CompareDocumentsParams, ctx: ToolContext) -> ToolResult:
    document_ids = list(dict.fromkeys(params.document_ids))
    missing = [d for d in document_ids if not (info := ctx.registry.find_by_id(d)) or info.status != "indexed"]
    if missing:
        raise ToolError(f"Documentos não encontrados ou ainda não indexados: {missing}")
    if len(document_ids) < 2:
        raise ToolError("Indica pelo menos dois documentos diferentes.")

    rows, refs = [], []
    for document_id in document_ids:
        row = _document_header(ctx, document_id)
        metadata = _metadata(ctx, document_id)
        if metadata and metadata.fields and ctx.document_types:
            doc_type = ctx.document_types.get(metadata.document_type)
            row["fields"] = {(doc_type.field(k).label if doc_type.field(k) else k): v for k, v in metadata.fields.items()}
        row["cells"] = {}
        for dimension in params.dimensions:
            sources = ctx.pipeline.retrieve_sources(
                question=dimension, top_k=params.excerpts_per_cell, filters=SearchFilters(document_id=document_id)
            )
            row["cells"][dimension] = [
                {"page": s.page, **({"section": s.section} if s.section else {}), "text": s.text[:MAX_CELL_CHARS]} for s in sources
            ]
            refs.extend(SourceRef(filename=s.filename, page=s.page, document_id=s.document_id) for s in sources)
        rows.append(row)

    return ToolResult(
        content={"dimensions": params.dimensions, "documents": rows},
        summary=f"{len(rows)} documentos × {len(params.dimensions)} dimensão(ões)",
        sources=refs,
    )
