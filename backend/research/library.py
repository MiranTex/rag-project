"""Documentos indexados vistos da área de pesquisa: cartões, facetas para os filtros e conversão de filtros."""

from collections import Counter, defaultdict

import numpy as np

from backend.models import DocumentInfo
from backend.repositories.contracts import DocumentRepository, ExtractionRepository
from backend.research.models import DocumentCard, ResearchFilters
from backend.services.document_types import BUILTIN_LABELS, DocumentTypes, section_label
from backend.services.search_filters import SearchFilters


def document_card(info: DocumentInfo, extractions: ExtractionRepository) -> DocumentCard:
    metadata = extractions.load_metadata(info.document_id)
    return DocumentCard(
        document_id=info.document_id,
        filename=info.filename,
        title=metadata.title or info.title,
        year=metadata.year or info.year,
        document_type=metadata.document_type or info.document_type,
        authors=metadata.authors,
        keywords=metadata.keywords,
        abstract=metadata.abstract,
        fields=metadata.fields,
        page_count=info.page_count,
    )


def indexed_document(registry: DocumentRepository, document_id: str) -> DocumentInfo | None:
    """Só documentos indexados existem para a área de pesquisa (os outros ainda não foram aprovados)."""
    info = registry.find_by_id(document_id)
    return info if info and info.status == "indexed" else None


def indexed_cards(registry: DocumentRepository, extractions: ExtractionRepository, document_ids: list[str]) -> list[DocumentCard]:
    cards = []
    for document_id in document_ids:
        if info := indexed_document(registry, document_id):
            cards.append(document_card(info, extractions))
    return cards


def to_search_filters(
    filters: ResearchFilters, types: DocumentTypes, scope: list[str] | None = None
) -> SearchFilters:
    """ValueError com as opções válidas se um tipo, campo ou secção não existir."""
    if filters.document_type and filters.document_type not in types.types:
        raise ValueError(f"Tipo de documento desconhecido: {filters.document_type}")
    filterable = {f.key for t in types.types.values() for f in t.fields if f.filterable}
    if unknown := set(filters.fields) - filterable:
        raise ValueError(f"Campos que não servem de filtro: {', '.join(sorted(unknown))}")
    sections = {s.key for t in types.types.values() for s in t.sections} | set(BUILTIN_LABELS)
    if unknown := set(filters.sections) - sections:
        raise ValueError(f"Secções desconhecidas: {', '.join(sorted(unknown))}")
    return SearchFilters(
        document_ids=scope,
        document_type=filters.document_type,
        year_from=filters.year_from,
        year_to=filters.year_to,
        sections=list(filters.sections),
        fields={key: value for key, value in filters.fields.items() if value},
    )


def facets(registry: DocumentRepository, extractions: ExtractionRepository, types: DocumentTypes) -> dict:
    """Valores existentes nos documentos indexados, para os filtros da pesquisa."""
    type_counts: Counter = Counter()
    years: list[int] = []
    field_values: dict[str, Counter] = defaultdict(Counter)
    for info in registry.list_documents():
        if info.status != "indexed":
            continue
        metadata = extractions.load_metadata(info.document_id)
        type_counts[metadata.document_type or info.document_type] += 1
        if metadata.year:
            years.append(metadata.year)
        for key, value in metadata.fields.items():
            for item in value if isinstance(value, list) else [value]:
                if item:
                    field_values[key][item] += 1

    filterable = {f.key: f.label for t in types.types.values() for f in t.fields if f.filterable}
    sections: dict[str, str] = {}
    for doc_type in types.types.values():
        for section in doc_type.sections:
            sections.setdefault(section.key, section_label(doc_type, section.key))
    return {
        "types": [
            {"key": t.key, "label": t.label, "count": type_counts.get(t.key, 0)} for t in types.types.values()
        ],
        "years": {"min": min(years), "max": max(years)} if years else None,
        "fields": [
            {"key": key, "label": label, "values": [value for value, _ in field_values[key].most_common(100)]}
            for key, label in filterable.items()
            if field_values[key]
        ],
        "sections": [{"key": key, "label": label} for key, label in sections.items()],
    }


def cosine(a: list[float], b: list[float]) -> float:
    """Os embeddings vêm normalizados (embeddings.py), mas normaliza-se na mesma por segurança."""
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb / norm) if norm else 0.0
