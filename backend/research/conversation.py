"""Proposta de projeto a partir de uma conversa do chat.

O LLM lê a conversa e propõe o título, o objetivo, as secções, os estados e as entradas iniciais. Nada aqui
conhece um assunto em particular: a estrutura é a que fizer sentido para a conversa (especificação de software,
parecer, plano de formação…), e a pessoa revê tudo antes de criar o projeto.

As fontes das respostas são numeradas [S1], [S2]… no texto enviado ao LLM; cada entrada indica os números em
que se apoia e aqui são trocados pelas páginas dos documentos, para a entrada ficar ligada ao original."""

import re
import unicodedata

from backend.research.llm import ChatCompletionClient, ask_json
from backend.research.models import (
    ConversationTurn,
    DraftItem,
    ProjectDraft,
    ProjectSection,
    ProjectStructure,
)

# O texto da conversa enviado ao LLM é cortado para caber no contexto de modelos pequenos.
MAX_ANSWER_CHARS = 4000
MAX_CONVERSATION_CHARS = 24000
MAX_ITEMS = 80

SYSTEM = (
    "Transformas uma conversa entre uma pessoa e um assistente (que respondeu com base em documentos) no ponto de "
    "partida de um projeto de trabalho em equipa. Não assumas nenhum tipo de projeto: escolhe as secções que fazem "
    "sentido para o que foi discutido e para o objetivo indicado pela pessoa. Divide o conteúdo em entradas "
    "pequenas e independentes (uma ideia, regra, requisito, decisão ou dúvida por entrada), para a equipa as poder "
    "comentar e aprovar uma a uma. Usa só informação que está na conversa; não inventes. Quando uma entrada vem de "
    "uma fonte, indica os números [S#] dessa fonte. Escreve em português de Portugal."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Título curto do projeto."},
        "description": {"type": "string", "description": "Duas ou três frases sobre o que é o projeto."},
        "objective": {"type": "string", "description": "Objetivo ou pergunta principal que orienta o projeto."},
        "sections": {
            "type": "array",
            "description": "Secções do projeto, pela ordem em que devem aparecer (3 a 10).",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string", "description": "O que deve entrar nesta secção."},
                    "ref_prefix": {
                        "type": "string",
                        "description": "Prefixo curto para numerar as entradas da secção (ex.: RF, R, Q), ou vazio.",
                    },
                },
                "required": ["title"],
            },
        },
        "statuses": {
            "type": "array",
            "description": "Estados que uma entrada pode ter, do primeiro ao último (ex.: proposto, aprovado). "
            "Vazio se não fizer sentido.",
            "items": {"type": "string"},
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "description": "Título da secção a que pertence."},
                    "title": {"type": "string"},
                    "text": {"type": "string", "description": "Conteúdo da entrada (markdown simples)."},
                    "sources": {"type": "array", "items": {"type": "integer"}, "description": "Números das fontes [S#]."},
                },
                "required": ["section", "title", "text"],
            },
        },
    },
    "required": ["title", "sections", "items"],
}


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:64] or "seccao"


def _numbered_sources(turns: list[ConversationTurn]) -> list[dict]:
    """Fontes únicas (documento + página) da conversa, pela ordem em que aparecem."""
    seen: dict[tuple[str, int | None], dict] = {}
    for turn in turns:
        for source in turn.sources:
            key = (source.document_id or source.filename, source.page)
            if key[0] and key not in seen:
                seen[key] = {"document_id": source.document_id, "filename": source.filename, "page": source.page}
    return list(seen.values())


def conversation_text(turns: list[ConversationTurn], sources: list[dict]) -> str:
    index = {(s["document_id"] or s["filename"], s["page"]): n for n, s in enumerate(sources, start=1)}
    blocks = []
    for turn in turns:
        refs = sorted({index[key] for s in turn.sources if (key := (s.document_id or s.filename, s.page)) in index})
        cited = f"\nFontes desta resposta: {', '.join(f'[S{n}]' for n in refs)}" if refs else ""
        blocks.append(f"Pessoa: {turn.question.strip()}\nAssistente: {turn.answer.strip()[:MAX_ANSWER_CHARS]}{cited}")
    text = "\n\n---\n\n".join(blocks)
    if len(text) > MAX_CONVERSATION_CHARS:
        # Ficam as partes mais recentes: costumam ser as que a pessoa quer levar para o projeto.
        text = "…\n\n" + text[-MAX_CONVERSATION_CHARS:]
    listing = "\n".join(f"[S{n}] {s['filename']}, p. {s['page']}" for n, s in enumerate(sources, start=1))
    return f"Fontes:\n{listing or '(nenhuma)'}\n\nConversa:\n\n{text}"


def _document_ids(sources: list[dict]) -> list[str]:
    return list(dict.fromkeys(s["document_id"] for s in sources if s["document_id"]))


def fallback_draft(turns: list[ConversationTurn]) -> ProjectDraft:
    """Sem LLM: um projeto com a conversa numa secção, uma entrada por pergunta."""
    sources = _numbered_sources(turns)
    first = next((t.question.strip() for t in turns if t.question.strip()), "Projeto")
    section = ProjectSection(key="conversa", title="Conversa", description="Perguntas e respostas que deram origem ao projeto.")
    items = [
        DraftItem(
            section=section.key,
            title=turn.question.strip()[:200],
            text=turn.answer.strip(),
            sources=[{"document_id": s.document_id, "filename": s.filename, "page": s.page} for s in turn.sources if s.document_id],
        )
        for turn in turns
        if turn.answer.strip()
    ]
    return ProjectDraft(
        title=first[:120],
        question=first,
        structure=ProjectStructure(sections=[section]),
        items=items,
        document_ids=_document_ids(sources),
        generated=False,
    )


def _clean_sections(raw: list) -> tuple[list[ProjectSection], dict[str, str], dict[str, str]]:
    """Secções com chave única; devolve também título→chave e chave→prefixo das referências."""
    sections: list[ProjectSection] = []
    by_title: dict[str, str] = {}
    prefixes: dict[str, str] = {}
    for entry in raw[:30]:
        if not isinstance(entry, dict) or not str(entry.get("title", "")).strip():
            continue
        title = " ".join(str(entry["title"]).split())[:200]
        if title.lower() in by_title:
            continue
        key = base = slug(title)
        n = 2
        while key in prefixes:
            key, n = f"{base[:60]}-{n}", n + 1
        sections.append(ProjectSection(key=key, title=title, description=str(entry.get("description", "")).strip()))
        by_title[title.lower()] = key
        prefixes[key] = re.sub(r"[^A-Za-z0-9]", "", str(entry.get("ref_prefix", "")))[:8].upper()
    return sections, by_title, prefixes


def draft_project(turns: list[ConversationTurn], goal: str, llm: ChatCompletionClient | None) -> ProjectDraft:
    turns = [t for t in turns if t.question.strip() or t.answer.strip()]
    if not turns:
        raise ValueError("A conversa está vazia.")
    sources = _numbered_sources(turns)
    user = conversation_text(turns, sources)
    if goal.strip():
        user = f"Objetivo indicado pela pessoa: {goal.strip()}\n\n{user}"
    result = ask_json(llm, SYSTEM, user, "propose_project", "Propõe a estrutura e as entradas iniciais do projeto.", SCHEMA)
    if not result:
        return fallback_draft(turns)

    sections, by_title, prefixes = _clean_sections(result.get("sections") or [])
    if not sections:
        return fallback_draft(turns)
    statuses = list(dict.fromkeys(" ".join(str(s).split()).lower() for s in result.get("statuses") or [] if str(s).strip()))[:12]

    counters: dict[str, int] = {}
    items: list[DraftItem] = []
    for raw in (result.get("items") or [])[:MAX_ITEMS]:
        if not isinstance(raw, dict) or not (str(raw.get("title", "")).strip() or str(raw.get("text", "")).strip()):
            continue
        section_title = " ".join(str(raw.get("section", "")).split()).lower()
        key = by_title.get(section_title) or next((k for t, k in by_title.items() if section_title and section_title in t), sections[0].key)
        ref = ""
        if prefixes.get(key):
            counters[key] = counters.get(key, 0) + 1
            ref = f"{prefixes[key]}-{counters[key]:03d}"
        cited = []
        for number in raw.get("sources") or []:
            if isinstance(number, int) and 1 <= number <= len(sources) and sources[number - 1] not in cited:
                cited.append(sources[number - 1])
        items.append(
            DraftItem(
                section=key,
                ref=ref,
                title=str(raw.get("title", "")).strip()[:300],
                text=str(raw.get("text", "")).strip(),
                status=statuses[0] if statuses else "",
                sources=[s for s in cited if s["document_id"]],
            )
        )

    return ProjectDraft(
        title=(str(result.get("title", "")).strip() or turns[0].question.strip() or "Projeto")[:200],
        description=str(result.get("description", "")).strip(),
        question=str(result.get("objective", "")).strip(),
        structure=ProjectStructure(sections=sections, statuses=statuses),
        items=items,
        document_ids=_document_ids(sources),
    )
