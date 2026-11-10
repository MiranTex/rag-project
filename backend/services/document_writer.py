import csv
import re
from pathlib import Path

from docx import Document

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def write_csv(path: Path, columns: list[str], rows: list[list], delimiter: str = ";") -> None:
    # utf-8-sig (BOM) para o Excel abrir acentos corretamente; ';' é o separador do Excel em PT.
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(columns)
        writer.writerows(rows)


def write_markdown(path: Path, title: str, markdown: str) -> None:
    body = markdown.strip()
    if not body.startswith("# "):
        body = f"# {title}\n\n{body}"
    path.write_text(body + "\n", encoding="utf-8")


def _add_runs(paragraph, text: str) -> None:
    """Adiciona texto ao parágrafo, convertendo **negrito**."""
    for i, part in enumerate(_BOLD.split(text)):
        if part:
            paragraph.add_run(part).bold = i % 2 == 1


def _add_table(document, lines: list[str]) -> None:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in row)]
    width = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=width)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            _add_runs(table.cell(r, c).paragraphs[0], cell)
            if r == 0:
                for run in table.cell(r, c).paragraphs[0].runs:
                    run.bold = True


def write_docx(path: Path, title: str, markdown: str) -> None:
    """Converte um subconjunto de markdown (títulos, listas, tabelas, negrito) para .docx."""
    document = Document()
    lines = markdown.strip().splitlines()
    if not (lines and lines[0].startswith("# ")):
        document.add_heading(title, level=0)

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            _add_table(document, table_lines)
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)", stripped)
        bullet = re.match(r"^[-*]\s+(.*)", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.*)", stripped)
        if heading:
            level = len(heading.group(1))
            document.add_heading(heading.group(2), level=0 if level == 1 else level - 1)
        elif bullet:
            _add_runs(document.add_paragraph(style="List Bullet"), bullet.group(1))
        elif numbered:
            _add_runs(document.add_paragraph(style="List Number"), numbered.group(1))
        else:
            _add_runs(document.add_paragraph(), stripped)
        i += 1

    document.save(str(path))
