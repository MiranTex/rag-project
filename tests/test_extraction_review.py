import json
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

import backend.api.documents as documents_api
from backend.api.security import current_user
from backend.auth.permissions import AuthenticatedUser
from backend.config import Settings
from backend.models import ReviewPage, User
from backend.repositories.sql import SqlDocumentRepository, SqlExtractionRepository, SqlJobQueue
from backend.services.document_renamer import DocumentRenamer
from backend.services.pdf_ingestion import ExtractedPage
from backend.services.extraction_review import ExtractionStore, garbled_ratio, validate_page
from tests.repository_fixtures import sql_engine


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

    def list_chunks(self, document_id=None):
        return [c for c in self.chunks.values() if c["metadata"]["document_id"] == document_id]

    def update_document_metadata(self, document_id, updates):
        for chunk in self.list_chunks(document_id):
            chunk["metadata"] = {**chunk["metadata"], **updates}
        return len(self.list_chunks(document_id))


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


def _user(user_id, *roles):
    return AuthenticatedUser.of(User(user_id=user_id, username=user_id, roles=list(roles), created_at="2026-11-03"))


def _image_only_pdf(path, lines):
    image = Image.new("L", (1700, 2200), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    for i, line in enumerate(lines):
        draw.text((120, 150 + i * 90), line, fill=0, font=font)
    image.save(path, "PDF", resolution=200)


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = sql_engine("sqlite", tmp_path)
    state = {
        "settings": Settings(_env_file=None, upload_dir=str(tmp_path / "uploads"), ocr_enabled=False),
        "registry": SqlDocumentRepository(engine),
        "store": SqlExtractionRepository(engine),
        "queue": SqlJobQueue(engine),
        "vectors": _FakeVectorStore(),
        "keywords": _FakeKeywordIndex(),
    }
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(documents_api, "get_settings", lambda: state["settings"])
    monkeypatch.setattr(documents_api, "get_registry", lambda: state["registry"])
    monkeypatch.setattr(documents_api, "get_extraction_store", lambda: state["store"])
    monkeypatch.setattr(documents_api, "get_job_queue", lambda: state["queue"])
    monkeypatch.setattr(documents_api, "get_vector_store", lambda: state["vectors"])
    monkeypatch.setattr(documents_api, "get_keyword_index", lambda: state["keywords"])
    monkeypatch.setattr(documents_api, "embed_texts", lambda model, texts: [[0.0] for _ in texts])
    monkeypatch.setattr(documents_api, "get_utility_llm", lambda: _FakeLLM())
    # Índice de documentos falso: os testes não tocam no Chroma nem no modelo de embeddings.
    state["profiles"] = []
    monkeypatch.setattr(documents_api, "get_profile_store", lambda: state["vectors"])
    renamer = DocumentRenamer(
        state["registry"], state["vectors"], state["keywords"], state["vectors"], documents_api.get_document_types()
    )
    monkeypatch.setattr(documents_api, "get_renamer", lambda: renamer)
    monkeypatch.setattr(
        documents_api,
        "upsert_profile",
        lambda store, model, info, metadata, doc_type, body: state["profiles"].append((info.document_id, doc_type.key, body)),
    )

    app = FastAPI()
    app.include_router(documents_api.router)
    # Utilizador do pedido: um gestor por defeito; os testes de permissões trocam-no.
    state["user"] = _user("gestor", "manager")
    app.dependency_overrides[current_user] = lambda: state["user"]
    state["client"] = TestClient(app)
    state["tmp_path"] = tmp_path
    # Sem workers em threads: os testes processam a fila quando querem.
    state["run_jobs"] = documents_api.build_job_runner().run_until_idle
    return state


def _post_pdf(env, lines):
    pdf_path = env["tmp_path"] / "scan.pdf"
    _image_only_pdf(pdf_path, lines)
    with pdf_path.open("rb") as f:
        res = env["client"].post("/documents/upload", files={"file": ("scan.pdf", f, "application/pdf")})
    assert res.status_code == 200, res.text
    return res.json()


def _doc(env, document_id):
    return env["registry"].find_by_id(document_id).model_dump()


def _upload(env, lines):
    """Carrega e corre a extração (que em produção corre em background)."""
    doc = _post_pdf(env, lines)["document"]
    env["run_jobs"]()
    return _doc(env, doc["document_id"])


def _approve(env, document_id):
    res = env["client"].post(f"/documents/{document_id}/approve")
    assert res.status_code == 200, res.text
    assert res.json()["document"]["status"] == "indexing"
    env["run_jobs"]()
    return _doc(env, document_id)


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

    assert _approve(env, doc_id)["status"] == "indexed"
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
    _approve(env, doc_id)

    res = client.post(f"/documents/{doc_id}/reindex")
    assert res.json()["document"]["status"] == "extracting"
    env["run_jobs"]()

    assert _doc(env, doc_id)["status"] == "pending_review"
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

    assert _approve(env, doc_id)["year"] == 2024

    chunks = [c["metadata"] for c in env["vectors"].chunks.values()]
    assert {c["section"] for c in chunks} == {"abstract", "introduction", "conclusion", "references"}
    assert all(c["title"] == "Recomendação de Livros" and c["year"] == 2024 for c in chunks)
    assert all(c["document_type"] == "academic" and c["course"] == "Licenciatura em EI" for c in chunks)
    # O vetor do documento usa o corpo sem as referências.
    [(profile_id, profile_type, body)] = env["profiles"]
    assert profile_id == doc_id and profile_type == "academic"
    assert "bibliotecas têm catálogos" in body and "Silva, J." not in body
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


def test_documents_are_stored_by_id_and_named_at_upload(env, monkeypatch):
    client = env["client"]
    uploads = env["tmp_path"] / "uploads"
    monkeypatch.setattr(documents_api, "extract_pages", lambda path, **kwargs: [ExtractedPage(1, THESIS_TEXT, "text")])
    doc = _upload(env, ["Contrato"])
    doc_id = doc["document_id"]

    # Em disco pelo id; no sistema, o nome vem da ficha proposta no upload.
    assert (uploads / f"{doc_id}.pdf").exists()
    assert (doc["filename"], doc["original_filename"], doc["name_source"]) == (
        "2024 - Recomendação de Livros - Ana Martins.pdf",
        "scan.pdf",
        "suggested",
    )

    # Corrigir a ficha depois do upload não muda o nome (a sugestão fica disponível na revisão).
    extraction = client.get(f"/documents/{doc_id}/extraction").json()
    metadata = {**extraction["metadata"], "title": "Livros nas Bibliotecas"}
    extraction = client.put(f"/documents/{doc_id}/metadata", json=metadata).json()
    assert extraction["document"]["filename"] == "2024 - Recomendação de Livros - Ana Martins.pdf"
    assert extraction["suggested_name"] == "2024 - Livros nas Bibliotecas - Ana Martins.pdf"

    # À mão continua a ser possível.
    doc = client.put(f"/documents/{doc_id}/name", json={"name": "Livros: estudo/2024"}).json()
    assert (doc["filename"], doc["name_source"]) == ("Livros estudo 2024.pdf", "manual")

    _approve(env, doc_id)
    assert {c["metadata"]["filename"] for c in env["vectors"].chunks.values()} == {"Livros estudo 2024.pdf"}

    # Num documento indexado, usar a sugestão muda o nome também nos excertos e no índice de palavras-chave.
    doc = client.put(f"/documents/{doc_id}/name", json={"name": None}).json()
    assert (doc["filename"], doc["name_source"]) == ("2024 - Livros nas Bibliotecas - Ana Martins.pdf", "suggested")
    assert {c["metadata"]["filename"] for c in env["vectors"].chunks.values()} == {doc["filename"]}
    assert {c["metadata"]["filename"] for c in env["keywords"].documents[doc_id]} == {doc["filename"]}

    # Extrair de novo mantém o nome.
    client.post(f"/documents/{doc_id}/reindex")
    env["run_jobs"]()
    assert _doc(env, doc_id)["filename"] == "2024 - Livros nas Bibliotecas - Ana Martins.pdf"

    client.delete(f"/documents/{doc_id}")
    assert not (uploads / f"{doc_id}.pdf").exists()


def test_documents_with_the_same_name_keep_separate_files_and_names(env):
    first = _post_pdf(env, ["Primeiro documento"])["document"]
    pdf_path = env["tmp_path"] / "scan.pdf"
    _image_only_pdf(pdf_path, ["Segundo documento diferente"])
    with pdf_path.open("rb") as f:
        second = env["client"].post("/documents/upload", files={"file": ("scan.pdf", f, "application/pdf")}).json()["document"]

    assert first["document_id"] != second["document_id"]
    uploads = env["tmp_path"] / "uploads"
    assert (uploads / f"{first['document_id']}.pdf").exists() and (uploads / f"{second['document_id']}.pdf").exists()
    # Dois "scan.pdf": o segundo nome no sistema é diferente.
    assert (first["filename"], second["filename"]) == ("scan.pdf", "scan (2).pdf")


def test_rename_rejects_invalid_names(env):
    doc_id = _upload(env, ["Contrato"])["document_id"]
    assert env["client"].put(f"/documents/{doc_id}/name", json={"name": " / "}).status_code == 422
    # Sem título na ficha não há nome sugerido.
    assert env["client"].put(f"/documents/{doc_id}/name", json={"name": None}).status_code == 422
    assert env["client"].put("/documents/nao-existe/name", json={"name": "x"}).status_code == 404


def test_upload_answers_before_extraction_and_rejects_duplicates(env):
    first = _post_pdf(env, ["Contrato"])
    assert (first["message"], first["document"]["status"]) == ("Na fila para extração.", "extracting")
    assert env["queue"].active_for_document(first["document"]["document_id"]).kind == "extract"

    # O mesmo ficheiro outra vez não cria outro documento.
    again = _post_pdf(env, ["Contrato"])
    assert again["document"]["document_id"] == first["document"]["document_id"]
    assert again["message"] == "Este documento já está a ser extraído."


def test_failed_extraction_is_reported_on_the_document(env, monkeypatch):
    def broken(path, **kwargs):
        raise ValueError("PDF corrompido")

    working = documents_api.extract_pages
    monkeypatch.setattr(documents_api, "extract_pages", broken)
    doc = _upload(env, ["Contrato"])

    assert (doc["status"], doc["error"]) == ("failed", "PDF corrompido")
    # Extrair de novo limpa o erro.
    monkeypatch.setattr(documents_api, "extract_pages", working)
    res = env["client"].post(f"/documents/{doc['document_id']}/reindex").json()["document"]
    assert (res["status"], res["error"]) == ("extracting", "")


def test_failed_indexing_returns_to_review(env, monkeypatch):
    doc_id = _upload(env, ["Contrato"])["document_id"]
    env["client"].put(f"/documents/{doc_id}/pages/1", json={"text": "Texto suficiente para passar a validação automática."})

    def chroma_down(model, texts):
        raise ConnectionError("Chroma indisponível")

    monkeypatch.setattr(documents_api, "embed_texts", chroma_down)
    doc = _approve(env, doc_id)

    assert (doc["status"], doc["error"]) == ("pending_review", "Chroma indisponível")


def test_one_job_at_a_time_per_document(env):
    doc_id = _upload(env, ["Contrato"])["document_id"]
    env["client"].put(f"/documents/{doc_id}/pages/1", json={"text": "Texto suficiente para passar a validação automática."})

    assert env["client"].post(f"/documents/{doc_id}/approve").status_code == 200
    assert env["client"].post(f"/documents/{doc_id}/approve").status_code == 409
    assert env["client"].post(f"/documents/{doc_id}/reindex").status_code == 409
    # Enquanto está na fila não se edita.
    assert env["client"].put(f"/documents/{doc_id}/pages/1", json={"excluded": True}).status_code == 409


def test_deleting_a_queued_document_cancels_its_job(env):
    doc_id = _post_pdf(env, ["Contrato"])["document"]["document_id"]

    assert env["client"].delete(f"/documents/{doc_id}").status_code == 200
    assert env["queue"].active_for_document(doc_id) is None
    assert env["run_jobs"]() == 0


def _text_pages(monkeypatch, text):
    """Extração com camada de texto (sem OCR): devolve sempre o mesmo texto na página 1."""
    monkeypatch.setattr(
        documents_api, "extract_pages", lambda path, **kwargs: [ExtractedPage(page=1, text=text, source="text")]
    )


def test_chat_only_user_cannot_see_or_change_documents(env):
    doc_id = _upload(env, ["Contrato"])["document_id"]
    env["user"] = _user("leitor", "chat")
    client = env["client"]

    assert client.get("/documents").status_code == 403
    assert client.get("/documents/types").status_code == 403
    assert client.get(f"/documents/{doc_id}/extraction").status_code == 403
    assert client.post(f"/documents/{doc_id}/approve").status_code == 403
    assert client.delete(f"/documents/{doc_id}").status_code == 403


def test_reviewer_corrects_and_approves_but_cannot_upload(env):
    doc_id = _upload(env, ["Contrato"])["document_id"]
    env["user"] = _user("revisora", "reviewer")
    client = env["client"]

    assert client.post(f"/documents/{doc_id}/reindex").status_code == 403
    res = client.put(f"/documents/{doc_id}/pages/1", json={"text": "Contrato de trabalho celebrado entre as partes."})
    assert res.status_code == 200
    doc = _approve(env, doc_id)
    assert (doc["status"], doc["uploaded_by"], doc["approved_by"]) == ("indexed", "gestor", "revisora")


def test_separate_approver_blocks_who_uploaded(env):
    env["settings"] = env["settings"].model_copy(update={"require_separate_approver": True})
    doc_id = _upload(env, ["Contrato"])["document_id"]
    env["client"].put(f"/documents/{doc_id}/pages/1", json={"text": "Contrato de trabalho celebrado entre as partes."})

    res = env["client"].post(f"/documents/{doc_id}/approve")
    assert res.status_code == 403

    env["user"] = _user("outro-gestor", "manager")
    assert _approve(env, doc_id)["approved_by"] == "outro-gestor"


def test_separate_approver_disables_auto_approve(env, monkeypatch):
    _text_pages(monkeypatch, "Contrato de trabalho celebrado entre a empresa e o trabalhador.")
    env["settings"] = env["settings"].model_copy(
        update={"auto_approve_clean_documents": True, "require_separate_approver": True}
    )
    assert _upload(env, ["Contrato"])["status"] == "pending_review"


def test_reindex_with_the_same_text_keeps_the_approval(env, monkeypatch):
    _text_pages(monkeypatch, "Contrato de trabalho celebrado entre a empresa e o trabalhador.")
    client = env["client"]
    doc_id = _upload(env, ["Contrato"])["document_id"]
    client.put(f"/documents/{doc_id}/metadata", json={"title": "Contrato revisto à mão"})
    approved = _approve(env, doc_id)

    env["user"] = _user("outro-gestor", "manager")
    assert client.post(f"/documents/{doc_id}/reindex").status_code == 200
    env["run_jobs"]()

    doc = _doc(env, doc_id)
    assert (doc["status"], doc["approved_by"], doc["uploaded_by"]) == ("indexed", "gestor", "outro-gestor")
    assert doc["approved_fingerprint"] == approved["approved_fingerprint"]
    # A ficha revista mantém-se (não se propõe outra).
    assert doc["title"] == "Contrato revisto à mão"
    assert doc_id in env["keywords"].documents


def test_reindex_with_different_text_needs_a_new_approval(env, monkeypatch):
    _text_pages(monkeypatch, "Contrato de trabalho celebrado entre a empresa e o trabalhador.")
    doc_id = _upload(env, ["Contrato"])["document_id"]
    _approve(env, doc_id)

    _text_pages(monkeypatch, "Contrato de trabalho com uma cláusula nova sobre teletrabalho.")
    env["client"].post(f"/documents/{doc_id}/reindex")
    env["run_jobs"]()

    assert _doc(env, doc_id)["status"] == "pending_review"
    assert env["vectors"].chunks == {}
