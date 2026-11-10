"""Filtros de pesquisa sobre os metadados dos excertos, iguais para o Chroma e para o índice de palavras-chave."""

from dataclasses import dataclass, field


@dataclass
class SearchFilters:
    document_id: str | None = None
    document_type: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    sections: list[str] = field(default_factory=list)
    # Campos "filterable" do tipo de documento (ver document_types.json), comparação exata.
    fields: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.document_id or self.document_type or self.year_from or self.year_to or self.sections or self.fields)

    def to_chroma_where(self) -> dict | None:
        conditions: list[dict] = []
        if self.document_id:
            conditions.append({"document_id": self.document_id})
        if self.document_type:
            conditions.append({"document_type": self.document_type})
        if self.year_from:
            conditions.append({"year": {"$gte": self.year_from}})
        if self.year_to:
            conditions.append({"year": {"$lte": self.year_to}})
        if self.sections:
            conditions.append({"section": {"$in": list(self.sections)}})
        for key, value in self.fields.items():
            conditions.append({key: value})
        if not conditions:
            return None
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def matches(self, metadata: dict) -> bool:
        if self.document_id and metadata.get("document_id") != self.document_id:
            return False
        if self.document_type and metadata.get("document_type") != self.document_type:
            return False
        year = metadata.get("year")
        if self.year_from and (year is None or year < self.year_from):
            return False
        if self.year_to and (year is None or year > self.year_to):
            return False
        if self.sections and metadata.get("section") not in self.sections:
            return False
        return all(metadata.get(key) == value for key, value in self.fields.items())
