"""Escrever: esqueleto do trabalho, rascunho do estado da arte com citações verificáveis e matriz de literatura.

O que vem da base (secções, excertos, páginas) é sempre devolvido; o LLM acrescenta perguntas, texto e resumos.
No estado da arte, cada frase tem de citar um excerto numerado; as que não citam vêm marcadas."""

import re

from backend.agent.tools.analysis import compare_documents
from backend.agent.tools.base import ToolContext
from backend.research.llm import ChatCompletionClient, ask_json
from backend.research.models import DocumentCard
from backend.services.search_filters import SearchFilters

# Secções que não se escrevem (a bibliografia gera-se à parte) nem servem de exemplo.
SKIPPED_SECTIONS = {"references", "appendix", "front_matter"}
EXCERPT_CHARS = 600


def _excerpt(source, number: int | None = None) -> dict:
    item = {
        "document_id": source.document_id,
        "filename": source.filename,
        "page": source.page,
        "section": source.section,
        "text": source.text[:EXCERPT_CHARS],
    }
    if number is not None:
        item["n"] = number
    return item


def skeleton(topic: str, work_type: str, scope: list[str] | None, ctx: ToolContext, llm: ChatCompletionClient | None) -> dict:
    """Índice do trabalho com as secções do tipo escolhido; por secção, perguntas a que deve responder,
    excertos relevantes (do projeto, se houver) e exemplos de como outros trabalhos da base a escreveram."""
    doc_type = ctx.document_types.get(work_type or None)
    sections = [s for s in doc_type.sections if s.key not in SKIPPED_SECTIONS]

    result = ask_json(
        llm,
        "Ajudas a planear um trabalho escrito. Para cada secção dada, escreves 2 a 4 perguntas concretas a que essa "
        "secção deve responder sobre o tema, em português.",
        f"Tipo de trabalho: {doc_type.label}\nTema: {topic}\nSecções:\n"
        + "\n".join(f"- {s.key}: {s.label}" for s in sections),
        "record_questions",
        "Regista as perguntas por secção.",
        {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}, "questions": {"type": "array", "items": {"type": "string"}}},
                        "required": ["key", "questions"],
                    },
                }
            },
            "required": ["sections"],
        },
    )
    questions = {
        entry.get("key"): [q for q in entry.get("questions") or [] if isinstance(q, str) and q.strip()]
        for entry in (result or {}).get("sections") or []
        if isinstance(entry, dict)
    }

    outline = []
    for section in sections:
        relevant = ctx.pipeline.retrieve_sources(
            question=f"{topic} {section.label}", top_k=4, filters=SearchFilters(document_ids=scope)
        )
        examples = ctx.pipeline.retrieve_sources(
            question=topic, top_k=2, filters=SearchFilters(document_type=doc_type.key, sections=[section.key])
        )
        outline.append(
            {
                "key": section.key,
                "label": section.label,
                "questions": questions.get(section.key, []),
                "relevant": [_excerpt(s) for s in relevant],
                "examples": [_excerpt(s) for s in examples],
            }
        )
    return {"topic": topic, "work_type": doc_type.key, "work_type_label": doc_type.label, "sections": outline}


def skeleton_markdown(data: dict) -> str:
    lines = [f"Tema: {data['topic']}", ""]
    for number, section in enumerate(data["sections"], start=1):
        lines.append(f"## {number}. {section['label']}")
        for question in section["questions"]:
            lines.append(f"- {question}")
        if section["relevant"]:
            lines.append("")
            lines.append("**Para ler:**")
            for excerpt in section["relevant"]:
                lines.append(f"- {excerpt['filename']}, p. {excerpt['page']}")
        lines.append("")
    return "\n".join(lines)


_CITATION = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def check_citations(markdown: str, source_count: int) -> dict:
    """Frases sem citação e citações a excertos que não existem (o modelo inventou um número)."""
    unsupported, invalid = [], set()
    for line in markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            sentence = sentence.strip()
            if len(sentence) < 25:
                continue
            numbers = [int(n) for group in _CITATION.findall(sentence) for n in re.split(r"\s*[,;]\s*", group)]
            if not numbers:
                unsupported.append(sentence)
            invalid.update(n for n in numbers if not 1 <= n <= source_count)
    return {"unsupported": unsupported, "invalid_citations": sorted(invalid)}


STATE_OF_ART_PROMPT = """Escreves o rascunho do estado da arte de um trabalho académico, em português, a partir de
excertos numerados de documentos. Regras:
- Usa só o que está nos excertos. Não acrescentes factos do teu conhecimento.
- Cada frase termina com a citação dos excertos em que se apoia, no formato [n] ou [n, m].
- Organiza por temas (subtítulos ##), não documento a documento; compara e relaciona os trabalhos.
- Se os excertos não chegam para um ponto, não o escrevas."""


def state_of_art(topic: str, cards: list[DocumentCard], ctx: ToolContext, llm) -> dict:
    """Rascunho com citações [n] a excertos numerados, a lista das fontes e as frases sem apoio.

    `llm` é o modelo principal (chat), não o pequeno: aqui escreve-se texto para a pessoa ler."""
    sources: list[dict] = []
    for card in cards:
        for source in ctx.pipeline.retrieve_sources(question=topic, top_k=2, filters=SearchFilters(document_id=card.document_id)):
            excerpt = _excerpt(source, number=len(sources) + 1)
            excerpt.update(title=card.title, year=card.year, authors=card.authors)
            sources.append(excerpt)
    if not sources:
        return {"markdown": "", "sources": [], "unsupported": [], "invalid_citations": []}

    listing = "\n\n".join(
        f"[{s['n']}] {(s['authors'][0] if s['authors'] else s['title'] or s['filename'])} ({s['year'] or 's.d.'}), "
        f"p. {s['page']}: {s['text']}"
        for s in sources
    )
    markdown = llm.chat(STATE_OF_ART_PROMPT, f"Tema: {topic}\n\nExcertos:\n\n{listing}").strip()
    return {"markdown": markdown, "sources": sources, **check_citations(markdown, len(sources))}


def fill_matrix(cards: list[DocumentCard], dimensions: list[str], ctx: ToolContext, llm: ChatCompletionClient | None) -> dict:
    """Matriz documentos × dimensões: excertos de cada célula (compare_documents) e um resumo curto do LLM."""
    content = compare_documents.run({"document_ids": [c.document_id for c in cards], "dimensions": dimensions}, ctx).content
    cells: dict[str, dict[str, dict]] = {}
    for row in content["documents"]:
        cells[row["document_id"]] = {dimension: {"excerpts": row["cells"].get(dimension, []), "summary": ""} for dimension in dimensions}

    listing = "\n\n".join(
        f"Documento {row['document_id']} ({row.get('title') or row['filename']}):\n"
        + "\n".join(
            f"  {dimension}: " + " | ".join(f"p. {e['page']}: {e['text']}" for e in row["cells"].get(dimension, []))
            for dimension in dimensions
        )
        for row in content["documents"]
    )
    result = ask_json(
        llm,
        "Resumes, numa frase curta em português, o que cada excerto diz sobre cada dimensão de uma matriz de "
        "revisão de literatura. Se os excertos não falam da dimensão, escreve 'Não referido'.",
        listing,
        "record_cells",
        "Regista o resumo de cada célula.",
        {
            "type": "object",
            "properties": {
                "cells": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "document_id": {"type": "string"},
                            "dimension": {"type": "string"},
                            "summary": {"type": "string"},
                        },
                        "required": ["document_id", "dimension", "summary"],
                    },
                }
            },
            "required": ["cells"],
        },
    )
    for cell in (result or {}).get("cells") or []:
        target = cells.get(cell.get("document_id"), {}).get(cell.get("dimension"))
        if target is not None and isinstance(cell.get("summary"), str):
            target["summary"] = cell["summary"].strip()
    return {"dimensions": dimensions, "cells": cells}
