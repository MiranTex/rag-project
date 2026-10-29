import json
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

import backend.api.documents as documents_api
from backend.config import Settings
from backend.models import ReviewPage
from backend.services.document_registry import DocumentRegistry
from backend.services.extraction_review import ExtractionStore, garbled_ratio, validate_page


def _codes(text, source="text", confidence=None):
    alerts = validate_page(text, source, confidence, min_text_chars=30, min_confidence=60, max_garbled_ratio=0.15)
    return [alert.code for alert in alerts]


def test_validate_page_clean_text_has_no_alerts():
    text = "O trabalhador obriga-se a cumprir o horário de 01/02/2024, com retribuição de 1.500,00 €."
    assert _codes(text) == []


def test_validate_page_flags_empty_and_short_text():
    assert _codes("   ") == ["empty"]
    assert _codes("Cláusula 1.ª") == ["short"]


def test_validate_page_flags_low_ocr_confidence_only_for_ocr():
    text = "Contrato de trabalho celebrado entre as partes abaixo identificadas."
    assert _codes(text, "ocr", 41.0) == ["low_confidence"]
    assert _codes(text, "manual", None) == []


def test_validate_page_flags_garbled_ocr():
    text = "Contrato |l~ rnnl d3_t ;;a tr@b4lho xkcd ºº| celebrado"
    assert garbled_ratio(text) > 0.15
    assert "garbled" in _codes(text)


def test_validate_page_flags_broken_encoding():
    assert "encoding" in _codes("O contrato de trabalho Ã© vÃ¡lido por um ano a partir de hoje.")
    assert "encoding" in _codes("O contrato (cid:31)(cid:42) de trabalho é válido por um ano.")


def test_extraction_store_roundtrip(tmp_path):
    store = ExtractionStore(str(tmp_path))
    pages = [ReviewPage(page=1, text="texto", source="text"), ReviewPage(page=2, text="", source="none", excluded=True)]

    store.save("doc", pages)
    assert store.load("doc") == pages

    store.delete("doc")
    assert store.load("doc") is None


class _FakeVectorStore:
    def __init__(self):
        self.chunks = {}

    def delete_document(self, document_id):
        self.chunks = {k: v for k, v in self.chunks.items() if v["metadata"]["document_id"] != document_id}

    def upsert_chunks(self, ids, embeddings, documents, metadatas):
        for chunk_id, text, metadata in zip(ids, documents, metadatas):
            self.chunks[chunk_id] = {"text": text, "metadata": metadata}


class _FakeKeywordIndex:
    def __init__(self):
        self.documents = {}

    def index_document(self, document_id, chunks):
        self.documents[document_id] = chunks

    def remove_document(self, document_id):
        self.documents.pop(document_id, None)


class _FakeLLM:
    def complete(self, messages, tools=None, tool_choice=None, temperature=0.2):
        arguments = {
            "document_type": "academic",
            "title": "Recomendação de Livros",
            "authors": ["Ana Martins"],
            "year": 2024,
            "course": "Engenharia Informática",
            "keywords": [],
        }
        return {"tool_calls": [{"function": {"arguments": json.dumps(arguments)}}]}


def _image_only_pdf(path, lines):
    image = Image.new("L", (1700, 2200), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    for i, line in enumerate(lines):
        draw.text((120, 150 + i * 90), line, fill=0, font=font)
    image.save(path, "PDF", resolution=200)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = {
        "settings": Settings(_env_file=None, upload_dir=str(tmp_path / "uploads"), ocr_enabled=False),
        "registry": DocumentRegistry(str(tmp_path / "docs.json")),
        "store": ExtractionStore(str(tmp_path / "extractions")),
        "vectors": _FakeVectorStore(),
        "keywords": _FakeKeywordIndex(),
    }
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(documents_api, "get_settings", lambda: state["settings"])
    monkeypatch.setattr(documents_api, "get_registry", lambda: state["registry"])
    monkeypatch.setattr(documents_api, "get_extraction_store", lambda: state["store"])
    monkeypatch.setattr(documents_api, "get_vector_store", lambda: state["vectors"])
    monkeypatch.setattr(documents_api, "get_keyword_index", lambda: state["keywords"])
    monkeypatch.setattr(documents_api, "embed_texts", lambda model, texts: [[0.0] for _ in texts])
    monkeypatch.setattr(documents_api, "get_utility_llm", lambda: _FakeLLM())

    app = FastAPI()
    app.include_router(documents_api.router)
    state["client"] = TestClient(app)
    state["tmp_path"] = tmp_path
    return state


def _upload(env, lines):
    pdf_path = env["tmp_path"] / "scan.pdf"
    _image_only_pdf(pdf_path, lines)
    with pdf_path.open("rb") as f:
        res = env["client"].post("/documents/upload", files={"file": ("scan.pdf", f, "application/pdf")})
    assert res.status_code == 200, res.text
    return res.json()["document"]


def test_upload_waits_for_review_then_manual_text_is_indexed(env):
    client = env["client"]
    doc = _upload(env, ["Contrato de trabalho"])

    # Sem OCR a página digitalizada fica vazia: entra na revisão com alerta e nada vai para o índice.
    assert doc["status"] == "pending_review"
    assert doc["alert_count"] == 1
    assert env["vectors"].chunks == {}

    doc_id = doc["document_id"]
    extraction = client.get(f"/documents/{doc_id}/extraction").json()
    assert extraction["pages"][0]["alerts"][0]["code"] == "empty"

    assert client.post(f"/documents/{doc_id}/approve").status_code == 400

    text = "Contrato de trabalho celebrado entre a empresa e o trabalhador."
    extraction = client.put(f"/documents/{doc_id}/pages/1", json={"text": text}).json()
    page = extraction["pages"][0]
    assert page["source"] == "manual" and page["edited"] and page["alerts"] == []
    assert extraction["document"]["alert_count"] == 0

    res = client.post(f"/documents/{doc_id}/approve")
    assert res.status_code == 200
    assert res.json()["document"]["status"] == "indexed"
    [chunk] = env["vectors"].chunks.values()
    assert chunk["metadata"]["extraction"] == "manual" and chunk["metadata"]["edited"] is True
    assert doc_id in env["keywords"].documents

    # Depois de indexado já não se edita sem voltar a extrair.
    assert client.put(f"/documents/{doc_id}/pages/1", json={"excluded": True}).status_code == 409


def test_excluded_pages_are_not_indexed(env):
    client = env["client"]
    doc_id = _upload(env, ["Contrato"])["document_id"]

    client.put(f"/documents/{doc_id}/pages/1", json={"text": "Texto suficiente para passar a validação automática."})
    client.put(f"/documents/{doc_id}/pages/1", json={"excluded": True})

    assert client.post(f"/documents/{doc_id}/approve").status_code == 400


def test_reindex_returns_document_to_review(env):
    client = env["client"]
    doc_id = _upload(env, ["Contrato"])["document_id"]
    client.put(f"/documents/{doc_id}/pages/1", json={"text": "Contrato de trabalho celebrado entre as partes."})
    client.post(f"/documents/{doc_id}/approve")

    res = client.post(f"/documents/{doc_id}/reindex")

    assert res.json()["document"]["status"] == "pending_review"
    assert env["vectors"].chunks == {}
    assert doc_id not in env["keywords"].documents


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract não instalado")
def test_auto_approve_indexes_clean_documents(env):
    env["settings"] = env["settings"].model_copy(update={"ocr_enabled": True, "auto_approve_clean_documents": True})

    doc = _upload(env, ["Contrato de trabalho", "Retribuição mensal de 1500 euros"])

    assert doc["status"] == "indexed"
    assert doc["chunk_count"] == 1


THESIS_TEXT = (
    "Resumo\nEste trabalho estuda recomendação de livros.\nPalavras-chave: recomendação; bibliotecas\n"
    "1. Introdução\nAs bibliotecas têm catálogos grandes e os leitores perdem-se neles.\n"
    "2. Conclusões\nO sistema melhora as sugestões.\n"
    "Referências\nSilva, J. (2020). Sistemas de recomendação. Lisboa: Editora."
)


def test_metadata_and_sections_flow_into_indexed_chunks(env):
    client = env["client"]
    doc_id = _upload(env, ["Contrato"])["document_id"]

    # Página sem texto: nada para propor na extração.
    extraction = client.get(f"/documents/{doc_id}/extraction").json()
    assert extraction["metadata"]["title"] == "" and extraction["sections"] == []

    extraction = client.put(f"/documents/{doc_id}/pages/1", json={"text": THESIS_TEXT}).json()
    assert [s["section"] for s in extraction["sections"]] == ["abstract", "introduction", "conclusion", "references"]
    assert extraction["references"] == ["Silva, J. (2020). Sistemas de recomendação. Lisboa: Editora."]

    # A sugestão só preenche campos vazios: o curso escrito à mão mantém-se.
    client.put(
        f"/documents/{doc_id}/metadata",
        json={"document_type": "academic", "fields": {"course": "Licenciatura em EI", "department": "x"}, "keywords": [" a ", ""]},
    )
    extraction = client.post(f"/documents/{doc_id}/metadata/suggest").json()
    metadata = extraction["metadata"]
    assert metadata["title"] == "Recomendação de Livros" and metadata["year"] == 2024
    # "department" é de outro tipo e foi descartado.
    assert metadata["fields"] == {"course": "Licenciatura em EI"}
    assert metadata["keywords"] == ["a"]
    assert extraction["document"]["title"] == "Recomendação de Livros"
    assert extraction["document"]["document_type"] == "academic"

    res = client.post(f"/documents/{doc_id}/approve")
    assert res.json()["document"]["year"] == 2024

    chunks = [c["metadata"] for c in env["vectors"].chunks.values()]
    assert {c["section"] for c in chunks} == {"abstract", "introduction", "conclusion", "references"}
    assert all(c["title"] == "Recomendação de Livros" and c["year"] == 2024 for c in chunks)
    assert all(c["document_type"] == "academic" and c["course"] == "Licenciatura em EI" for c in chunks)
    assert env["store"].load_metadata(doc_id).references == [
        "Silva, J. (2020). Sistemas de recomendação. Lisboa: Editora."
    ]
    assert client.put(f"/documents/{doc_id}/metadata", json={"title": "x"}).status_code == 409


def test_unknown_document_type_is_rejected(env):
    doc_id = _upload(env, ["Contrato"])["document_id"]
    res = env["client"].put(f"/documents/{doc_id}/metadata", json={"document_type": "receita"})
    assert res.status_code == 422


def test_document_types_endpoint_lists_default_first(env):
    types = env["client"].get("/documents/types").json()
    assert types[0]["key"] == "generic"
    academic = next(t for t in types if t["key"] == "academic")
    assert {"key": "course", "label": "Curso", "type": "text", "filterable": True}.items() <= next(
        f for f in academic["fields"] if f["key"] == "course"
    ).items()
