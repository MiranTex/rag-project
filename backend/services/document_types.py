"""Tipos de documento da base de conhecimento, lidos de um ficheiro JSON (ver backend/document_types.json).

Cada instituição define os seus tipos: que campos a ficha tem além do núcleo comum (título, autores, ano,
palavras-chave, resumo) e que títulos de secção se reconhecem.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

FieldKind = Literal["text", "list", "people"]

# Nome do documento no sistema (ver document_naming.py).
DEFAULT_NAME_PATTERN = "{year} - {title}"
NAME_PLACEHOLDERS = {"title", "year", "authors", "type", "date"}


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    kind: FieldKind = "text"
    hint: str = ""
    filterable: bool = False


@dataclass(frozen=True)
class SectionDef:
    key: str
    label: str
    pattern: re.Pattern


@dataclass(frozen=True)
class DocumentType:
    key: str
    label: str
    description: str
    fields: tuple[FieldDef, ...] = ()
    sections: tuple[SectionDef, ...] = ()
    name_pattern: str = ""
    # Secções onde fica o que está em aberto (trabalho futuro, limitações, recomendações).
    open_sections: tuple[str, ...] = ()

    def field(self, key: str) -> FieldDef | None:
        return next((f for f in self.fields if f.key == key), None)


@dataclass(frozen=True)
class DocumentTypes:
    types: dict[str, DocumentType]
    default: str
    union_sections: tuple[SectionDef, ...] = field(default=())
    name_pattern: str = DEFAULT_NAME_PATTERN

    def name_pattern_for(self, doc_type: DocumentType) -> str:
        return doc_type.name_pattern or self.name_pattern

    def get(self, key: str | None) -> DocumentType:
        return self.types.get(key or "", self.types[self.default])


# Chaves reservadas: o código usa-as para o índice e para capítulos sem nome conhecido.
FRONT_MATTER = "front_matter"
CHAPTER = "chapter"
BUILTIN_LABELS = {FRONT_MATTER: "Elementos iniciais", CHAPTER: "Capítulo"}
CORE_FIELDS = {"title", "authors", "year", "keywords", "abstract", "document_type"}


def _section(raw: dict) -> SectionDef:
    patterns = raw.get("patterns") or []
    if not patterns:
        raise ValueError(f"secção {raw.get('key')!r} sem patterns")
    return SectionDef(
        key=raw["key"],
        label=raw.get("label", raw["key"]),
        pattern=re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE),
    )


def _check_name_pattern(owner: str, pattern: str, field_keys: set[str]) -> None:
    unknown = set(re.findall(r"\{(\w+)\}", pattern)) - NAME_PLACEHOLDERS - field_keys
    if unknown:
        raise ValueError(f"name_pattern de {owner!r} usa campos desconhecidos: {sorted(unknown)}")


def parse_document_types(config: dict) -> DocumentTypes:
    types: dict[str, DocumentType] = {}
    for key, raw in config["types"].items():
        fields = []
        for f in raw.get("fields", []):
            if f["key"] in CORE_FIELDS:
                raise ValueError(f"tipo {key!r}: o campo {f['key']!r} já faz parte do núcleo da ficha")
            kind = f.get("type", "text")
            if kind not in ("text", "list", "people"):
                raise ValueError(f"tipo {key!r}: campo {f['key']!r} com type inválido {kind!r}")
            # Só valores escalares vão para os metadados do Chroma.
            fields.append(FieldDef(f["key"], f.get("label", f["key"]), kind, f.get("hint", ""), bool(f.get("filterable")) and kind == "text"))
        sections = [_section(s) for s in raw.get("sections", [])]
        if any(s.key in BUILTIN_LABELS for s in sections):
            raise ValueError(f"tipo {key!r}: {sorted(BUILTIN_LABELS)} são chaves reservadas")
        name_pattern = raw.get("name_pattern", "")
        _check_name_pattern(key, name_pattern, {f.key for f in fields})
        open_sections = tuple(raw.get("open_sections", []))
        unknown = set(open_sections) - {s.key for s in sections}
        if unknown:
            raise ValueError(f"tipo {key!r}: open_sections com secções que o tipo não tem: {sorted(unknown)}")
        types[key] = DocumentType(
            key, raw.get("label", key), raw.get("description", ""), tuple(fields), tuple(sections), name_pattern, open_sections
        )

    default = config.get("default") or next(iter(types))
    if default not in types:
        raise ValueError(f"tipo por defeito {default!r} não existe")

    # Antes de saber o tipo (para encontrar o resumo que ajuda a classificá-lo) usam-se todas as secções.
    union: dict[str, SectionDef] = {}
    for doc_type in types.values():
        for s in doc_type.sections:
            union.setdefault(s.key, s)
            if union[s.key] is not s:
                merged = f"{union[s.key].pattern.pattern}|{s.pattern.pattern}"
                union[s.key] = SectionDef(s.key, union[s.key].label, re.compile(merged, re.IGNORECASE))
    name_pattern = config.get("name_pattern") or DEFAULT_NAME_PATTERN
    _check_name_pattern("(geral)", name_pattern, set())
    return DocumentTypes(types=types, default=default, union_sections=tuple(union.values()), name_pattern=name_pattern)


def load_document_types(path: str) -> DocumentTypes:
    return parse_document_types(json.loads(Path(path).read_text(encoding="utf-8")))


def section_label(doc_type: DocumentType, key: str) -> str:
    if key in BUILTIN_LABELS:
        return BUILTIN_LABELS[key]
    return next((s.label for s in doc_type.sections if s.key == key), key)
