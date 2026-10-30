"""Contrato de DocumentRepository e ExtractionRepository: todas as implementações têm de passar."""

import json

import pytest
from sqlalchemy import inspect

from backend.models import DocumentInfo, DocumentMetadata, Job, PageAlert, ReviewPage
from backend.repositories.legacy_import import import_legacy_json
from backend.repositories.sql import SqlDocumentRepository, SqlExtractionRepository, metadata_obj
from backend.services.document_registry import DocumentRegistry
from backend.services.extraction_review import ExtractionStore
from tests.repository_fixtures import SQL_BACKENDS, sql_engine


@pytest.fixture(params=["json", *SQL_BACKENDS])
def repos(request, tmp_path):
    if request.param == "json":
        return DocumentRegistry(str(tmp_path / "docs.json")), ExtractionStore(str(tmp_path / "extractions"))
    engine = sql_engine(request.param, tmp_path)
    return SqlDocumentRepository(engine), SqlExtractionRepository(engine)


def _doc(document_id="d1", **overrides) -> DocumentInfo:
    values = {
        "document_id": document_id,
        "filename": "2024 - Relatório.pdf",
        "original_filename": "scan 01.pdf",
        "storage_name": f"{document_id}.pdf",
        "name_source": "suggested",
        "sha256": f"sha-{document_id}",
        "created_at": f"2026-10-29T10:00:0{document_id[-1]}+00:00",
        "chunk_count": 12,
        "status": "indexed",
        "page_count": 4,
        "alert_count": 1,
        "title": "Relatório de atividades",
        "year": 2024,
        "document_type": "generic",
        "error": "",
    }
    return DocumentInfo(**{**values, **overrides})


def test_documents_round_trip_every_field(repos):
    documents, _ = repos
    doc = _doc()
    documents.add_or_replace(doc)

    assert documents.find_by_id("d1") == doc
    assert documents.find_by_hash("sha-d1") == doc
    assert documents.find_by_id("nope") is None and documents.find_by_hash("nope") is None


def test_documents_replace_and_list_in_creation_order(repos):
    documents, _ = repos
    documents.add_or_replace(_doc("d2"))
    documents.add_or_replace(_doc("d1"))
    documents.add_or_replace(_doc("d2", status="failed", error="PDF corrompido", year=None))

    assert [d.document_id for d in documents.list_documents()] == ["d1", "d2"]
    replaced = documents.find_by_id("d2")
    assert (replaced.status, replaced.error, replaced.year) == ("failed", "PDF corrompido", None)


def test_documents_remove(repos):
    documents, _ = repos
    documents.add_or_replace(_doc())

    assert documents.remove("d1") is True
    assert documents.remove("d1") is False
    assert documents.list_documents() == []


PAGES = [
    ReviewPage(page=1, text="Capa\nTítulo", source="text"),
    ReviewPage(
        page=2,
        text="OCR fraco",
        source="ocr",
        ocr_confidence=41.5,
        alerts=[PageAlert(code="low_confidence", message="Confiança baixa.")],
        excluded=True,
    ),
    ReviewPage(page=3, text="", source="none", edited=False),
]


def test_extraction_pages_round_trip_and_replace(repos):
    _, extractions = repos
    extractions.save("d1", PAGES)
    assert extractions.load("d1") == PAGES

    extractions.save("d1", PAGES[:1])
    assert extractions.load("d1") == PAGES[:1]
    assert extractions.load("other") is None


def test_metadata_round_trip_and_delete(repos):
    _, extractions = repos
    metadata = DocumentMetadata(
        document_type="academic",
        title="Recomendação",
        authors=["Ana"],
        year=2024,
        keywords=["livros"],
        abstract="Resumo.",
        fields={"course": "EI", "advisors": ["João", "Rita"]},
        references=["Silva (2020)."],
        auto_filled=True,
    )
    assert extractions.load_metadata("d1") == DocumentMetadata()

    extractions.save("d1", PAGES)
    extractions.save_metadata("d1", metadata)
    extractions.save_metadata("d1", metadata.model_copy(update={"title": "Outro"}))
    assert extractions.load_metadata("d1") == metadata.model_copy(update={"title": "Outro"})

    extractions.delete("d1")
    assert extractions.load("d1") is None
    assert extractions.load_metadata("d1") == DocumentMetadata()


@pytest.mark.parametrize("kind", SQL_BACKENDS)
def test_migrations_match_tables_and_models(kind, tmp_path):
    """O esquema criado pelas migrações tem de bater com as tabelas do código e com os modelos: apanha um campo
    novo sem migração."""
    engine = sql_engine(kind, tmp_path)
    inspector = inspect(engine)

    for table in metadata_obj.sorted_tables:
        migrated = {column["name"] for column in inspector.get_columns(table.name)}
        assert migrated == {column.name for column in table.columns}, table.name
    assert {c["name"] for c in inspector.get_columns("documents")} == set(DocumentInfo.model_fields)
    assert {c["name"] for c in inspector.get_columns("extraction_pages")} == {"document_id", *ReviewPage.model_fields}
    assert {c["name"] for c in inspector.get_columns("jobs")} == set(Job.model_fields)


def test_legacy_json_is_imported_once(tmp_path):
    legacy_docs = DocumentRegistry(str(tmp_path / "documents.json"))
    legacy_docs.add_or_replace(_doc())
    legacy_extractions = ExtractionStore(str(tmp_path / "extractions"))
    legacy_extractions.save("d1", PAGES)
    legacy_extractions.save_metadata("d1", DocumentMetadata(title="Relatório"))
    # Registo antigo, sem os campos novos.
    raw = json.loads((tmp_path / "documents.json").read_text())
    for key in ("original_filename", "storage_name", "name_source", "error"):
        raw[0].pop(key)
    (tmp_path / "documents.json").write_text(json.dumps(raw))

    engine = sql_engine("sqlite", tmp_path)
    documents, extractions = SqlDocumentRepository(engine), SqlExtractionRepository(engine)
    args = (documents, extractions, str(tmp_path / "documents.json"), str(tmp_path / "extractions"))

    assert import_legacy_json(*args) == 1
    imported = documents.find_by_id("d1")
    assert imported.filename == "2024 - Relatório.pdf" and imported.storage_name == ""
    assert extractions.load("d1") == PAGES
    assert extractions.load_metadata("d1").title == "Relatório"
    # O ficheiro fica como cópia de segurança e não volta a ser importado.
    assert (tmp_path / "documents.json.imported").exists()
    assert import_legacy_json(*args) == 0
