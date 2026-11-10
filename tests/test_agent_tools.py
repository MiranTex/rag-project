import csv
from types import SimpleNamespace

import pytest
from docx import Document

from backend.agent.tools import ToolContext, ToolError, build_registry
from backend.agent.tools.calculations import safe_eval
from backend.agent.tools.documents import merge_chunk_texts
from backend.services.export_store import ExportStore


class _FakeVectorStore:
    def __init__(self, chunks):
        self.chunks = chunks

    def list_chunks(self, document_id=None):
        return [c for c in self.chunks if c["metadata"]["document_id"] == document_id]


class _FakeRegistry:
    def find_by_id(self, document_id):
        if document_id == "doc-1":
            return SimpleNamespace(document_id="doc-1", filename="contrato.pdf", chunk_count=3, status="indexed")
        return None

    def list_documents(self):
        return [self.find_by_id("doc-1")]


def _chunk(page, index, text):
    return {"text": text, "metadata": {"document_id": "doc-1", "page": page, "chunk_index": index}}


@pytest.fixture
def ctx(tmp_path):
    chunks = [
        _chunk(1, 0, "Cláusula 1. A retribuição mensal é de 1500 euros"),
        _chunk(1, 1, "mensal é de 1500 euros, paga 14 vezes por ano."),
        _chunk(2, 2, "Cláusula 2. O contrato inicia a 01/02/2024."),
    ]
    return ToolContext(
        pipeline=None,
        vector_store=_FakeVectorStore(chunks),
        registry=_FakeRegistry(),
        export_store=ExportStore(str(tmp_path)),
    )


@pytest.fixture
def registry():
    return build_registry()


def run(registry, ctx, name, **arguments):
    return registry.get(name).run(arguments, ctx)


def test_registry_exposes_valid_openai_schemas(registry):
    for item in registry.all():
        schema = item.schema()
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["type"] == "object"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("(1650 - 1500) / 1500 * 100", 10.0), ("round(1250.5 * 14, 2)", 17507.0), ("max(1, 2) + abs(-3)", 5), ("2 ** 10", 1024)],
)
def test_safe_eval(expression, expected):
    assert safe_eval(expression) == expected


@pytest.mark.parametrize("expression", ["__import__('os').system('id')", "open('x')", "[1, 2]", "a + 1", "9 ** 9999", "1 / 0", "1.250,50 * 2"])
def test_safe_eval_rejects_unsafe_or_invalid(expression):
    with pytest.raises(ToolError):
        safe_eval(expression)


def test_percentage_change(registry, ctx):
    result = run(registry, ctx, "percentage_change", old_value=1500, new_value=1650)
    assert result.content["difference"] == 150
    assert result.content["percent_change"] == 10.0


def test_date_difference_calendar_breakdown(registry, ctx):
    result = run(registry, ctx, "date_difference", start_date="01/02/2024", end_date="2026-10-28")
    assert (result.content["years"], result.content["months"], result.content["days"]) == (2, 8, 27)
    assert result.content["total_days"] == 1000


def test_date_add_clamps_end_of_month(registry, ctx):
    result = run(registry, ctx, "date_add", start_date="2024-01-31", months=1)
    assert result.content["result_date"] == "2024-02-29"


def test_invalid_arguments_raise_tool_error(registry, ctx):
    with pytest.raises(ToolError):
        registry.get("date_difference").run('{"start_date": 5', ctx)
    with pytest.raises(ToolError):
        run(registry, ctx, "date_difference", start_date="ontem")


def test_merge_chunk_texts_removes_overlap():
    merged = merge_chunk_texts(["A retribuição mensal é de 1500 euros", "mensal é de 1500 euros, paga 14 vezes."])
    assert merged == "A retribuição mensal é de 1500 euros, paga 14 vezes."


def test_read_document_groups_pages_and_reports_sources(registry, ctx):
    result = run(registry, ctx, "read_document", document_id="doc-1", page_start=1, page_end=1)
    assert result.content["pages"] == [
        {"page": 1, "text": "Cláusula 1. A retribuição mensal é de 1500 euros, paga 14 vezes por ano."}
    ]
    assert [(s.filename, s.page) for s in result.sources] == [("contrato.pdf", 1)]


def test_read_document_unknown_id(registry, ctx):
    with pytest.raises(ToolError):
        run(registry, ctx, "read_document", document_id="nope")


def test_export_csv_never_overwrites(registry, ctx):
    args = {"filename": "Cláusulas do contrato", "columns": ["cláusula", "valor"], "rows": [["Retribuição", 1500]]}
    first = run(registry, ctx, "export_csv", **args)
    second = run(registry, ctx, "export_csv", **args)

    assert first.exports[0].name == "Clausulas-do-contrato.csv"
    assert second.exports[0].name == "Clausulas-do-contrato-2.csv"
    path = ctx.export_store.resolve(first.exports[0].name)
    with path.open(encoding="utf-8-sig") as handle:
        assert list(csv.reader(handle, delimiter=";")) == [["cláusula", "valor"], ["Retribuição", "1500"]]


def test_export_csv_rejects_ragged_rows(registry, ctx):
    with pytest.raises(ToolError):
        run(registry, ctx, "export_csv", filename="x", columns=["a", "b"], rows=[["1"]])


def test_export_document_docx(registry, ctx):
    content = "## Partes\n- **Empregadora:** ACME\n\n| Campo | Valor |\n|---|---|\n| Salário | 1500 |"
    result = run(registry, ctx, "export_document", filename="resumo", title="Resumo", content=content)

    doc = Document(str(ctx.export_store.resolve(result.exports[0].name)))
    texts = [p.text for p in doc.paragraphs]
    assert "Resumo" in texts and "Partes" in texts and "Empregadora: ACME" in texts
    assert doc.tables[0].cell(1, 1).text == "1500"


def test_export_store_resolve_blocks_path_traversal(tmp_path):
    store = ExportStore(str(tmp_path / "exports"))
    (tmp_path / "secret.txt").write_text("x")
    assert store.resolve("../secret.txt") is None
