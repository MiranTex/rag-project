"""Referências bibliográficas geradas da ficha dos documentos (APA 7, NP 405 / ISO 690 e BibTeX).

São um ponto de partida: a ficha nem sempre tem tudo (editora, local), por isso convém rever antes de entregar."""

import re
import unicodedata

from backend.research.models import CitationStyle, DocumentCard

# Campos da ficha onde costuma estar a entidade responsável, por ordem de preferência.
INSTITUTION_FIELDS = ("institution", "organization", "department")
TYPE_LABELS = {"academic": "Dissertação", "procedure": "Procedimento"}

_PARTICLES = {"da", "de", "do", "das", "dos", "e", "van", "von", "del", "di"}


def _split_name(name: str) -> tuple[str, list[str]]:
    """("Martins", ["Ana", "Rita"]) a partir de "Ana Rita Martins"; aceita também "Martins, Ana Rita"."""
    name = " ".join(name.split())
    if "," in name:
        surname, given = (part.strip() for part in name.split(",", 1))
        return surname, given.split()
    parts = name.split()
    if len(parts) == 1:
        return parts[0], []
    return parts[-1], parts[:-1]


def _initials(given: list[str]) -> str:
    """As partículas (da, de, dos…) não dão inicial: "João da" -> "J."."""
    return " ".join(f"{g[0]}." for g in given if g and g.lower() not in _PARTICLES)


def _institution(card: DocumentCard) -> str:
    for key in INSTITUTION_FIELDS:
        value = card.fields.get(key)
        if value:
            return value if isinstance(value, str) else ", ".join(value)
    return ""


def _title(card: DocumentCard) -> str:
    return card.title or re.sub(r"\.pdf$", "", card.filename, flags=re.IGNORECASE)


def _year(card: DocumentCard) -> str:
    return str(card.year) if card.year else "s.d."


def apa(card: DocumentCard) -> str:
    names = []
    for author in card.authors:
        surname, given = _split_name(author)
        names.append(f"{surname}, {_initials(given)}".rstrip(", "))
    if len(names) > 1:
        authors = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        authors = names[0] if names else ""
    kind = TYPE_LABELS.get(card.document_type)
    parts = [f"{authors} ({_year(card)})." if authors else f"{_title(card)} ({_year(card)})."]
    if authors:
        parts.append(_title(card) + (f" [{kind}]." if kind else "."))
    elif kind:
        parts.append(f"[{kind}].")
    if institution := _institution(card):
        parts.append(f"{institution}.")
    return " ".join(parts)


def iso690(card: DocumentCard) -> str:
    names = []
    for author in card.authors:
        surname, given = _split_name(author)
        names.append(f"{surname.upper()}, {' '.join(given)}".rstrip(", "))
    parts = [f"{'; '.join(names)}." if names else ""]
    parts.append(f"{_title(card)}.")
    kind = TYPE_LABELS.get(card.document_type)
    institution = _institution(card)
    tail = ", ".join(part for part in (kind, institution, _year(card)) if part)
    parts.append(f"{tail}.")
    return " ".join(part for part in parts if part)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _bibtex_key(card: DocumentCard) -> str:
    surname = _split_name(card.authors[0])[0] if card.authors else "anon"
    first_word = next((w for w in re.findall(r"\w+", _ascii(_title(card))) if len(w) > 3), "doc")
    return re.sub(r"[^a-z0-9]", "", f"{_ascii(surname)}{card.year or ''}{first_word}".lower())


def bibtex(card: DocumentCard) -> str:
    entry = "mastersthesis" if card.document_type == "academic" else "techreport"
    institution_key = "school" if entry == "mastersthesis" else "institution"
    fields = {
        "author": " and ".join(card.authors),
        "title": "{" + _title(card) + "}",
        "year": str(card.year or ""),
        institution_key: _institution(card),
        "keywords": ", ".join(card.keywords),
    }
    body = ",\n".join(f"  {key} = {{{value}}}" for key, value in fields.items() if value)
    return f"@{entry}{{{_bibtex_key(card)},\n{body}\n}}"


FORMATTERS = {"apa": apa, "iso690": iso690, "bibtex": bibtex}


def bibliography(cards: list[DocumentCard], style: CitationStyle) -> list[str]:
    """Uma referência por documento, por ordem alfabética do primeiro autor (ou do título)."""

    def sort_key(card: DocumentCard) -> str:
        first = _split_name(card.authors[0])[0] if card.authors else _title(card)
        return _ascii(first).lower()

    return [FORMATTERS[style](card) for card in sorted(cards, key=sort_key)]
