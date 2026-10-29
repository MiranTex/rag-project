"""Nome de um documento no sistema, gerado a partir da ficha com o padrão do tipo (ver document_types.json).

O nome aparece na lista de documentos, nas fontes das respostas e nas citações do agente. O ficheiro em disco
não muda: está guardado pelo id do documento (ou, nos documentos antigos, pelo nome original).

Padrão: "{year} - {title}". Campos: title, year, authors (primeiro autor), type (nome do tipo), date (data do
carregamento, AAAA-MM-DD) e os campos próprios do tipo. Partes separadas por " - " em que todos os campos estão
vazios desaparecem; "[...]" marca um grupo opcional que desaparece se algum campo lá dentro estiver vazio.
"""

import re
import unicodedata

from backend.models import DocumentInfo, DocumentMetadata
from backend.services.document_types import DocumentType

MAX_NAME_CHARS = 120
MAX_TITLE_CHARS = 90
SEPARATOR = " - "

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_OPTIONAL = re.compile(r"\[([^\[\]]*)\]")
# Caracteres que não podem aparecer num nome de ficheiro (Windows incluído) e controlo.
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


def _values(metadata: DocumentMetadata, doc_type: DocumentType, info: DocumentInfo) -> dict[str, str]:
    values = {
        "title": _shorten(metadata.title, MAX_TITLE_CHARS),
        "year": str(metadata.year or ""),
        "authors": metadata.authors[0] if metadata.authors else "",
        "type": doc_type.label,
        "date": info.created_at[:10],
    }
    for field in doc_type.fields:
        value = metadata.fields.get(field.key, "")
        values[field.key] = value[0] if isinstance(value, list) and value else value if isinstance(value, str) else ""
    return values


def render_name(pattern: str, values: dict[str, str]) -> str:
    def fill(text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), text)

    def optional(match: re.Match) -> str:
        keys = _PLACEHOLDER.findall(match.group(1))
        return fill(match.group(1)) if all(values.get(k) for k in keys) else ""

    parts = []
    for part in pattern.split(SEPARATOR):
        keys = _PLACEHOLDER.findall(part)
        if keys and not any(values.get(k) for k in keys):
            continue
        parts.append(fill(_OPTIONAL.sub(optional, part)).strip())
    return SEPARATOR.join(part for part in parts if part)


def clean_name(name: str) -> str:
    """Nome seguro para mostrar e para descarregar: sem caracteres proibidos, espaços simples, com .pdf."""
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"\.pdf$", "", name.strip(), flags=re.IGNORECASE)
    name = " ".join(_FORBIDDEN.sub(" ", name).split()).strip(" .-")
    return f"{name[:MAX_NAME_CHARS].rstrip(' .-')}.pdf" if name else ""


def unique_name(name: str, taken: set[str]) -> str:
    """Acrescenta " (2)", " (3)"... se outro documento já tiver o nome (sem distinguir maiúsculas)."""
    taken_lower = {t.lower() for t in taken}
    if name.lower() not in taken_lower:
        return name
    stem = name[: -len(".pdf")]
    counter = 2
    while f"{stem} ({counter}).pdf".lower() in taken_lower:
        counter += 1
    return f"{stem} ({counter}).pdf"


def suggest_name(metadata: DocumentMetadata, doc_type: DocumentType, pattern: str, info: DocumentInfo) -> str:
    """Nome sugerido, ou "" se a ficha não tiver título (sem título o nome original diz mais)."""
    if not metadata.title.strip():
        return ""
    values = _values(metadata, doc_type, info)
    name = render_name(pattern, values)
    # Se não couber, encolhe o título (pela palavra) em vez de cortar o fim: o autor ou a versão ficam inteiros.
    excess = len(name) - MAX_NAME_CHARS
    if excess > 0 and values["title"]:
        values["title"] = _shorten(values["title"], max(len(values["title"]) - excess - 1, 20))
        name = render_name(pattern, values)
    return clean_name(name)
