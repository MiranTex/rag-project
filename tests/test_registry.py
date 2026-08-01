from backend.models import DocumentInfo
from backend.services.document_registry import DocumentRegistry


def test_registry_add_and_find(tmp_path) -> None:
    registry = DocumentRegistry(path=str(tmp_path / "docs.json"))
    doc = DocumentInfo(
        document_id="1",
        filename="a.pdf",
        sha256="abc",
        created_at="2026-01-01T00:00:00+00:00",
        chunk_count=3,
    )

    registry.add_or_replace(doc)
    found = registry.find_by_hash("abc")

    assert found is not None
    assert found.document_id == "1"


def test_registry_find_by_id_and_remove(tmp_path) -> None:
    registry = DocumentRegistry(path=str(tmp_path / "docs.json"))
    doc = DocumentInfo(
        document_id="2",
        filename="b.pdf",
        sha256="def",
        created_at="2026-01-01T00:00:00+00:00",
        chunk_count=5,
    )

    registry.add_or_replace(doc)

    found = registry.find_by_id("2")
    assert found is not None
    assert found.filename == "b.pdf"

    removed = registry.remove("2")
    assert removed is True

    missing = registry.find_by_id("2")
    assert missing is None
