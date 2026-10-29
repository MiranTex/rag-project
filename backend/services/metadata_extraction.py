import json
import logging
import re

from backend.agent.runner import ChatCompletionClient
from backend.models import DocumentMetadata
from backend.services.document_structure import Heading, Segment, find_abstract, find_keywords, find_references

logger = logging.getLogger(__name__)

# "Prof. Doutor", "Profª Drª", "Eng." antes do nome de um orientador.
_TITLES = re.compile(r"^(?:(?:prof(?:essor|essora|ª|a)?|dr(?:ª|a)?|doutor(?:a)?|eng(?:º|ª|enheiro|enheira)?|mestre|msc|phd)\.?\s+)+", re.IGNORECASE)

FRONT_PAGES = 3
FRONT_CHARS = 6000

METADATA_PROMPT = """
Recebes o início de um documento (capa, folha de rosto e resumo), normalmente um trabalho final de curso,
dissertação ou relatório académico. Regista os metadados com a ferramenta record_metadata.

Regras:
- Usa apenas o que está escrito no texto. Se um campo não aparece, deixa-o vazio (ou null no ano).
- Não traduzas nem reformules: copia o título e os nomes como estão, corrigindo só maiúsculas a mais.
- authors: quem escreveu o trabalho. advisors: orientadores e coorientadores, sem o título (Prof., Dr.).
- course: o curso ou grau (ex.: "Licenciatura em Engenharia Informática").
- year: o ano de entrega ou de defesa.
- Se o documento não for um trabalho académico (contrato, fatura...), preenche só o título.
""".strip()

RECORD_METADATA_TOOL = {
    "type": "function",
    "function": {
        "name": "record_metadata",
        "description": "Regista os metadados encontrados no documento.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "authors": {"type": "array", "items": {"type": "string"}},
                "advisors": {"type": "array", "items": {"type": "string"}},
                "year": {"type": ["integer", "null"]},
                "course": {"type": "string"},
                "institution": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "authors", "advisors", "year", "course", "institution", "keywords"],
        },
    },
}


def _clean_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [" ".join(str(v).split()) for v in values if str(v).strip()][:20]


def _clean_year(value) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def _ask_llm(llm: ChatCompletionClient, front_text: str) -> dict:
    message = llm.complete(
        [{"role": "system", "content": METADATA_PROMPT}, {"role": "user", "content": front_text}],
        tools=[RECORD_METADATA_TOOL],
        tool_choice={"type": "function", "function": {"name": "record_metadata"}},
        temperature=0.0,
    )
    return json.loads(message["tool_calls"][0]["function"]["arguments"])


def _front_text(pages: list[tuple[int, str]], abstract: str) -> str:
    text = "\n\n".join(f"[Página {page}]\n{body}" for page, body in pages[:FRONT_PAGES])[:FRONT_CHARS]
    if abstract and abstract[:200] not in text:
        text += f"\n\n[Resumo]\n{abstract[:1500]}"
    return text


def propose_metadata(
    pages: list[tuple[int, str]],
    segments: list[Segment],
    headings: list[Heading],
    llm: ChatCompletionClient | None,
) -> DocumentMetadata:
    """Resumo, palavras-chave e referências saem do texto por regras (exatos); título, autores, ano, curso...
    vêm do LLM. Se o LLM falhar, devolve só a parte das regras e auto_filled=False."""
    abstract = find_abstract(segments, headings)
    front = "\n".join(text for _, text in pages[:FRONT_PAGES])
    abstract_text = "\n".join(s.text for s in segments if s.section == "abstract")
    keywords = find_keywords(f"{front}\n{abstract_text}")
    metadata = DocumentMetadata(abstract=abstract, keywords=keywords, references=find_references(segments))
    if llm is None or not any(text.strip() for _, text in pages):
        return metadata

    try:
        proposed = _ask_llm(llm, _front_text(pages, abstract))
    except Exception:
        logger.warning("Extração de metadados com o LLM falhou; ficha fica por preencher", exc_info=True)
        return metadata

    return metadata.model_copy(
        update={
            "title": " ".join(str(proposed.get("title") or "").split()),
            "authors": _clean_list(proposed.get("authors")),
            "advisors": [_TITLES.sub("", advisor) for advisor in _clean_list(proposed.get("advisors"))],
            "year": _clean_year(proposed.get("year")),
            "course": " ".join(str(proposed.get("course") or "").split()),
            "institution": " ".join(str(proposed.get("institution") or "").split()),
            # As palavras-chave escritas no documento valem mais do que as que o LLM deduz.
            "keywords": keywords or _clean_list(proposed.get("keywords"))[:15],
            "auto_filled": True,
        }
    )
