import json
import logging
import re

from backend.agent.runner import ChatCompletionClient
from backend.models import DocumentMetadata, FieldValue
from backend.services.document_structure import find_abstract, find_keywords, find_references, split_sections
from backend.services.document_types import DocumentType, DocumentTypes

logger = logging.getLogger(__name__)

# "Prof. Doutor", "Profª Drª", "Eng." antes de um nome (campos do tipo "people").
_TITLES = re.compile(r"^(?:(?:prof(?:essor|essora|ª|a)?|dr(?:ª|a)?|doutor(?:a)?|eng(?:º|ª|enheiro|enheira)?|mestre|msc|phd)\.?\s+)+", re.IGNORECASE)

FRONT_PAGES = 3
FRONT_CHARS = 6000

METADATA_PROMPT = """
Recebes o início de um documento (capa, primeiras páginas e resumo) de uma base de conhecimento.
Sobre esta base de conhecimento: {knowledge_base}

Regista a ficha do documento com a ferramenta record_metadata.

Tipos de documento:
{types}

Regras:
- Escolhe o tipo que melhor descreve o documento; na dúvida, usa "{default}".
- Usa apenas o que está escrito no texto. Se um campo não aparece, deixa-o vazio (ou null no ano).
- Não traduzas nem reformules: copia o título e os nomes como estão, corrigindo só maiúsculas a mais.
- authors: quem escreveu ou é responsável pelo documento (pessoas ou entidades).
- year: o ano do documento (entrega, publicação, aprovação ou assinatura).
- Os campos marcados com "(só <tipo>)" só se preenchem para esse tipo.
""".strip()


def _clean(value: str) -> str:
    return " ".join(str(value).split())


def _clean_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_clean(v) for v in values if str(v).strip()][:20]


def _clean_year(value) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def clean_fields(doc_type: DocumentType, raw: dict) -> dict[str, FieldValue]:
    """Mantém só os campos do tipo, com o formato certo; descarta os vazios."""
    fields: dict[str, FieldValue] = {}
    for field in doc_type.fields:
        value = raw.get(field.key)
        if field.kind == "text":
            cleaned = _clean(value) if isinstance(value, str) else ""
        else:
            cleaned = _clean_list(value if isinstance(value, list) else [value] if value else [])
            if field.kind == "people":
                cleaned = [_TITLES.sub("", name) for name in cleaned]
        if cleaned:
            fields[field.key] = cleaned
    return fields


def _record_tool(types: DocumentTypes) -> dict:
    properties: dict = {
        "title": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "year": {"type": ["integer", "null"]},
        "keywords": {"type": "array", "items": {"type": "string"}},
    }
    if len(types.types) > 1:
        properties["document_type"] = {"type": "string", "enum": list(types.types)}
    # Campos próprios de todos os tipos numa só chamada; a descrição diz a que tipo pertencem.
    for doc_type in types.types.values():
        for field in doc_type.fields:
            schema = {"type": "string"} if field.kind == "text" else {"type": "array", "items": {"type": "string"}}
            owners = properties.get(field.key, {}).get("description", "")
            label = f"{field.label}{f': {field.hint}' if field.hint else ''}"
            own = f"(só {doc_type.key}) {label}"
            schema["description"] = f"{owners} | {own}" if owners else own
            properties[field.key] = schema
    return {
        "type": "function",
        "function": {
            "name": "record_metadata",
            "description": "Regista a ficha encontrada no documento.",
            "parameters": {"type": "object", "properties": properties, "required": ["title", "authors", "year", "keywords"]},
        },
    }


def _ask_llm(llm: ChatCompletionClient, types: DocumentTypes, knowledge_base: str, front_text: str) -> dict:
    system = METADATA_PROMPT.format(
        knowledge_base=knowledge_base,
        types="\n".join(f"- {t.key}: {t.label}. {t.description}" for t in types.types.values()),
        default=types.default,
    )
    message = llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": front_text}],
        tools=[_record_tool(types)],
        tool_choice={"type": "function", "function": {"name": "record_metadata"}},
        temperature=0.0,
    )
    return json.loads(message["tool_calls"][0]["function"]["arguments"])


def _front_text(pages: list[tuple[int, str]], abstract: str) -> str:
    text = "\n\n".join(f"[Página {page}]\n{body}" for page, body in pages[:FRONT_PAGES])[:FRONT_CHARS]
    if abstract and abstract[:200] not in text:
        text += f"\n\n[Resumo]\n{abstract[:1500]}"
    return text


def rule_based_metadata(pages: list[tuple[int, str]], doc_type: DocumentType) -> DocumentMetadata:
    """Resumo, palavras-chave e referências, só com regras e as secções do tipo."""
    segments, headings = split_sections(pages, doc_type.sections)
    abstract = find_abstract(segments, headings)
    front = "\n".join(text for _, text in pages[:FRONT_PAGES])
    abstract_text = "\n".join(s.text for s in segments if s.section == "abstract")
    return DocumentMetadata(
        document_type=doc_type.key,
        abstract=abstract,
        keywords=find_keywords(f"{front}\n{abstract_text}"),
        references=find_references(segments),
    )


def propose_metadata(
    pages: list[tuple[int, str]],
    types: DocumentTypes,
    llm: ChatCompletionClient | None,
    knowledge_base: str = "",
) -> DocumentMetadata:
    """O LLM escolhe o tipo e propõe título, autores, ano e os campos do tipo; resumo, palavras-chave e
    referências saem do texto por regras. Se o LLM falhar, fica o tipo por defeito, só com as regras."""
    # Antes de saber o tipo, o resumo procura-se com as secções de todos os tipos.
    union = DocumentType("_all", "", "", sections=types.union_sections)
    provisional = rule_based_metadata(pages, union)
    fallback = rule_based_metadata(pages, types.get(None))
    if llm is None or not any(text.strip() for _, text in pages):
        return fallback

    try:
        proposed = _ask_llm(llm, types, knowledge_base, _front_text(pages, provisional.abstract))
    except Exception:
        logger.warning("Extração da ficha com o LLM falhou; fica por preencher", exc_info=True)
        return fallback

    doc_type = types.get(proposed.get("document_type"))
    by_rules = rule_based_metadata(pages, doc_type)
    return by_rules.model_copy(
        update={
            "title": _clean(proposed.get("title") or ""),
            "authors": _clean_list(proposed.get("authors")),
            "year": _clean_year(proposed.get("year")),
            # As palavras-chave escritas no documento valem mais do que as que o LLM deduz.
            "keywords": by_rules.keywords or _clean_list(proposed.get("keywords"))[:15],
            "fields": clean_fields(doc_type, proposed),
            "auto_filled": True,
        }
    )
