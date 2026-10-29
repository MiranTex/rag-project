"""Estrutura de trabalhos académicos (TFC, dissertações) a partir do texto extraído, só com regras.

Deteta os títulos de secção linha a linha (PT e EN), ignora as linhas do índice e, a partir das secções,
obtém o resumo, as palavras-chave e as entradas da bibliografia.
"""

import re
from dataclasses import dataclass

SECTION_LABELS: dict[str, str] = {
    "front_matter": "Elementos iniciais",
    "abstract": "Resumo",
    "introduction": "Introdução",
    "literature": "Estado da arte",
    "methodology": "Metodologia",
    "development": "Desenvolvimento",
    "results": "Resultados",
    "conclusion": "Conclusões",
    "future_work": "Trabalho futuro",
    "limitations": "Limitações",
    "references": "Referências",
    "appendix": "Anexos",
}

# A ordem conta: "conclusões e trabalho futuro" é conclusão, "trabalho futuro" sozinho é trabalho futuro.
_HEADING_PATTERNS: list[tuple[str, str]] = [
    ("abstract", r"resumo|abstract"),
    ("introduction", r"introdu[çc][ãa]o|introduction"),
    (
        "literature",
        r"estado d[ao] arte|revis[ãa]o (?:da |de )?literatura|enquadramento te[óo]rico|fundamenta[çc][ãa]o te[óo]rica"
        r"|trabalhos? relacionados?|related work|literature review|state of the art|background",
    ),
    ("methodology", r"metodologia(?: de investiga[çc][ãa]o)?|m[ée]todos?|materiais e m[ée]todos|methodology|methods?"),
    (
        "results",
        r"resultados(?: e discuss[ãa]o)?|(?:an[áa]lise|apresenta[çc][ãa]o) (?:e discuss[ãa]o )?(?:d[eo]s? )?resultados"
        r"|an[áa]lise e discuss[ãa]o|discuss[ãa]o(?: d[eo]s? resultados)?"
        r"|avalia[çc][ãa]o|results(?: and discussion)?|discussion|evaluation",
    ),
    (
        "conclusion",
        r"conclus(?:[ãa]o|[õo]es)(?: e trabalhos? futuros?)?|considera[çc][õo]es finais|conclusions?(?: and future work)?",
    ),
    ("future_work", r"trabalhos? futuros?|perspe(?:c)?tivas? futuras?|future work"),
    ("limitations", r"limita[çc][õo]es(?: do (?:estudo|trabalho))?|limitations"),
    ("references", r"refer[êe]ncias(?: bibliogr[áa]ficas)?|bibliografia|references|bibliography"),
    ("appendix", r"(?:anexos?|ap[êe]ndices?|appendix|appendices)(?:\s+(?:[\dIVXLC]+|[A-Z]))?"),
    (
        "front_matter",
        r"agradecimentos|acknowledge?ments|dedicat[óo]ria|[íi]ndice(?: geral)?|sum[áa]rio"
        r"|lista de (?:figuras|tabelas|quadros|abreviaturas|siglas|acr[óo]nimos)|table of contents|contents",
    ),
]
_HEADINGS = [(section, re.compile(rf"(?:{pattern})", re.IGNORECASE)) for section, pattern in _HEADING_PATTERNS]

# "Capítulo 2 –", "2.", "5.1" antes do título.
_NUMBERING = re.compile(r"^(?:(?:cap[íi]tulo|chapter)\s+[\dIVXLC]+\s*[-–—:.]?\s*)?(?:\d{1,2}(?:\.\d{1,2})*\.?\s+)?", re.IGNORECASE)
# Capítulo numerado que não é nenhuma secção conhecida ("3. Arquitetura do sistema").
_CHAPTER = re.compile(r"^(?:(?:cap[íi]tulo|chapter)\s+[\dIVXLC]+\b.*|\d{1,2}\.?\s+[A-ZÀ-Ý][^.!?;:]{2,60})$")
# "CAPÍTULO 2" sozinho numa linha: o título do capítulo vem na linha seguinte.
_CHAPTER_MARKER = re.compile(r"^(?:cap[íi]tulo|chapter)\s+[\dIVXLC]+\.?$", re.IGNORECASE)
# Reticências até ao número da página: linha de índice em qualquer parte do documento.
_DOT_LEADERS = re.compile(r"\.{3,}|…|\s\.\s\.")
# "Título 12": dentro de um índice é uma entrada; fora dele pode ser um título real ("2 COVID – 19").
_ENDS_WITH_PAGE = re.compile(r"\s\d{1,3}$")
# Títulos que abrem um índice ou uma lista com números de página.
_TOC_HEADING = re.compile(
    r"[íi]ndice(?: geral)?|sum[áa]rio|table of contents|contents|lista de (?:figuras|tabelas|quadros|gr[áa]ficos)",
    re.IGNORECASE,
)
# Contador de página que o pypdf cola à primeira linha: "16/80 2 COVID – 19".
_PAGE_COUNTER = re.compile(r"^\d{1,4}\s*/\s*\d{1,4}\s+")

MAX_HEADING_CHARS = 80
MIN_HEADINGS = 2


@dataclass
class Segment:
    page: int
    section: str | None
    text: str
    heading_index: int | None = None


@dataclass
class Heading:
    section: str
    page: int
    text: str


def _strip_page_counter(line: str) -> str:
    return _PAGE_COUNTER.sub("", line.strip())


def classify_heading(line: str, in_toc: bool = False) -> str | None:
    """Devolve a secção se a linha for um título de secção, ou None. Dentro de um índice (in_toc),
    linhas que terminam no número da página são entradas do índice e não títulos."""
    line = _strip_page_counter(line)
    if not line or len(line) > MAX_HEADING_CHARS or _DOT_LEADERS.search(line):
        return None
    if in_toc and _ENDS_WITH_PAGE.search(line):
        return None
    title = _NUMBERING.sub("", line).strip().rstrip(":").strip()
    for section, pattern in _HEADINGS:
        if pattern.fullmatch(title):
            return section
    if _CHAPTER.match(line):
        return "development"
    return None


def split_sections(pages: list[tuple[int, str]]) -> tuple[list[Segment], list[Heading]]:
    """Divide o texto em segmentos (página, secção). Documentos com menos de MIN_HEADINGS títulos
    (contratos, faturas...) não têm estrutura de trabalho académico: ficam sem secção."""
    headings: list[Heading] = []
    segments: list[Segment] = []
    section: str | None = None
    heading_index: int | None = None
    in_toc = False

    for page, text in pages:
        buffer: list[str] = []
        chapter_marker: str | None = None
        for line in text.splitlines():
            if _CHAPTER_MARKER.match(_strip_page_counter(line)):
                chapter_marker = _strip_page_counter(line)
                buffer.append(line)
                continue
            found = classify_heading(line, in_toc)
            if chapter_marker:
                # A linha a seguir a "Capítulo N" é sempre um título, conhecido ou não.
                found = found or ("development" if len(line.strip()) <= MAX_HEADING_CHARS else None)
                heading_text = f"{chapter_marker} {_strip_page_counter(line)}"
                chapter_marker = None
            else:
                heading_text = _strip_page_counter(line)
                # Linhas numeradas na bibliografia, anexos ou antes do corpo são entradas/listas, não capítulos.
                if found == "development" and section in ("references", "appendix", "front_matter", None):
                    found = None
            if found is None:
                buffer.append(line)
                continue
            # O marcador "Capítulo N" pertence ao capítulo novo, não ao anterior.
            carried = [buffer.pop()] if buffer and _CHAPTER_MARKER.match(_strip_page_counter(buffer[-1])) else []
            if buffer:
                segments.append(Segment(page, section, "\n".join(buffer), heading_index))
            buffer = carried
            section = found
            heading_index = len(headings)
            headings.append(Heading(section=found, page=page, text=heading_text))
            # O índice acaba no primeiro título que não seja outro índice/lista.
            in_toc = bool(_TOC_HEADING.fullmatch(_NUMBERING.sub("", heading_text).strip().rstrip(":")))
            buffer.append(line)
        if buffer:
            segments.append(Segment(page, section, "\n".join(buffer), heading_index))

    if len(headings) < MIN_HEADINGS:
        return [Segment(s.page, None, s.text) for s in segments], []
    for segment in segments:
        if segment.section is None:
            segment.section = "front_matter"
    return segments, headings


def _section_text(segments: list[Segment], heading_index: int) -> str:
    return "\n".join(s.text for s in segments if s.heading_index == heading_index)


# "Palavras -Chave:" (o pypdf às vezes mete um espaço antes do hífen).
_KEYWORDS_PT = r"palavras\s*-?\s*chave"
_KEYWORDS_EN = r"key\s*words"
_KEYWORDS_LINE = re.compile(rf"^\s*(?:{_KEYWORDS_PT}|{_KEYWORDS_EN})\s*[:.\-–—]\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def find_keywords(text: str) -> list[str]:
    """Linha "Palavras-chave: a; b; c"; só usa "Keywords:" se não houver a versão portuguesa."""
    match = None
    for label in (_KEYWORDS_PT, _KEYWORDS_EN):
        match = re.search(rf"^\s*{label}\s*[:.\-–—]\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if match:
            break
    if not match:
        return []
    raw = match.group(1).strip().rstrip(".")
    separator = ";" if ";" in raw else ","
    return [kw.strip(" .·") for kw in raw.split(separator) if kw.strip(" .·")][:15]


def find_abstract(segments: list[Segment], headings: list[Heading], max_chars: int = 3000) -> str:
    """Texto do primeiro resumo (normalmente o português), sem o título nem a linha de palavras-chave."""
    for index, heading in enumerate(headings):
        if heading.section != "abstract":
            continue
        lines = _section_text(segments, index).splitlines()[1:]
        body = [line for line in lines if not _KEYWORDS_LINE.match(line)]
        return " ".join(body).strip()[:max_chars]
    return ""


# Início de uma entrada: "[12]", "12.", "Silva, J.", "SILVA, J." ou "Silva Santos, Ana".
_REFERENCE_START = re.compile(
    r"^(?:\[\d{1,3}\]|\d{1,3}\.\s"
    r"|[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\-]+(?: [A-ZÀ-Ý][A-Za-zÀ-ÿ'’\-]+)?,\s*[A-ZÀ-Ý]"
    r"|[A-ZÀ-Ý]{2,}(?: [A-ZÀ-Ý]{2,})*,\s)"
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def find_references(segments: list[Segment], max_entries: int = 500) -> list[str]:
    """Entradas da bibliografia: cada linha que começa como uma referência abre uma entrada nova,
    as restantes continuam a anterior. Só ficam entradas com ano, para descartar cabeçalhos e ruído."""
    lines = [
        line.strip()
        for segment in segments
        if segment.section == "references"
        for line in segment.text.splitlines()
        if line.strip() and classify_heading(line) != "references"
    ]
    entries: list[str] = []
    for line in lines:
        # Uma entrada sem ano ainda vai a meio da lista de autores ("…, Jiang, H.," / "Raat, H., & Zhou, H. (2020)"):
        # a linha seguinte continua-a, mesmo que comece como um apelido.
        if not entries or (_REFERENCE_START.match(line) and (line.startswith("[") or _YEAR.search(entries[-1]))):
            entries.append(line)
        else:
            # Palavra hifenizada na quebra de linha: "contra-" + "to".
            joiner = "" if entries[-1].endswith("-") and line[:1].islower() else " "
            entries[-1] = (entries[-1][:-1] if joiner == "" else entries[-1]) + joiner + line
    return [entry for entry in entries if _YEAR.search(entry) and len(entry) >= 20][:max_entries]
