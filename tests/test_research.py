import json

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.chat as chat_api
import backend.api.feedback as feedback_api
import backend.api.research as research_api
import backend.api.research_projects as projects_api
import backend.research.access as access
import backend.research.discovery as discovery
from backend.agent.tools.base import ToolContext, ToolError
from backend.api.security import current_user
from backend.auth.authenticators import create_local_user
from backend.auth.permissions import AuthenticatedUser
from backend.config import Settings
from backend.models import DocumentInfo, DocumentMetadata, ReviewPage, SourceChunk
from backend.repositories.research_sql import SqlFeedbackRepository, SqlResearchRepository
from backend.repositories.sql import SqlDocumentRepository, SqlExtractionRepository, SqlUserRepository
from backend.research.bibliography import apa, bibliography, bibtex, iso690
from backend.research.discovery import _kmeans, check_claims, split_claims, split_paragraphs, theme_map
from backend.research.models import AnswerFeedback, Comment, DocumentCard, NotebookItem, Project, ProjectMember, SavedSearch
from backend.research.writing import check_citations
from backend.services.document_types import load_document_types
from backend.services.export_store import ExportStore
from backend.services.search_filters import SearchFilters
from backend.services.vector_store import VectorStore
from tests.repository_fixtures import SQL_BACKENDS, sql_engine

TYPES = load_document_types("backend/document_types.json")
NOW = "2026-01-01T10:00:00+00:00"


# ---------------------------------------------------------------- repositório


@pytest.mark.parametrize("backend", SQL_BACKENDS)
def test_research_repository_contract(backend, tmp_path):
    repo = SqlResearchRepository(sql_engine(backend, tmp_path))
    mine = Project(project_id="p1", owner_id="ana", title="Bibliotecas", created_at=NOW, updated_at=NOW)
    shared = Project(project_id="p2", owner_id="rui", title="Partilhado", created_at=NOW, updated_at="2026-11-04")
    other = Project(project_id="p3", owner_id="rui", title="Só do Rui", created_at=NOW, updated_at=NOW)
    for project in (mine, shared, other):
        repo.save_project(project)
    repo.set_member(ProjectMember(project_id="p2", user_id="ana", role="viewer"))
    repo.set_member(ProjectMember(project_id="p2", user_id="ana", role="editor"))

    assert [p.project_id for p in repo.list_projects_for("ana")] == ["p2", "p1"]
    assert repo.list_members("p2") == [ProjectMember(project_id="p2", user_id="ana", role="editor")]

    note = NotebookItem(item_id="i1", project_id="p1", kind="note", title="Ideia", text="Usar Recomendação híbrida",
                        tags=["método"], created_by="ana", created_at=NOW, updated_at=NOW)
    excerpt = NotebookItem(item_id="i2", project_id="p1", kind="excerpt", text="Outro texto", source={"page": 3},
                           created_by="ana", created_at="2026-11-04", updated_at="2026-11-04")
    repo.save_item(note)
    repo.save_item(excerpt)
    assert [i.item_id for i in repo.list_items("p1")] == ["i2", "i1"]
    assert repo.list_items("p1", query="recomendação") == [note]
    assert repo.list_items("p1", kind="excerpt") == [excerpt]
    assert repo.count_items("p1") == 2

    repo.add_comment(Comment(comment_id="c1", project_id="p1", item_id="i1", author_id="rui", text="Boa", created_at=NOW))
    repo.add_comment(Comment(comment_id="c2", project_id="p1", author_id="rui", text="Geral", created_at=NOW))
    repo.delete_item("i1")
    assert [c.comment_id for c in repo.list_comments("p1")] == ["c2"]

    repo.save_matrix("p1", {"dimensions": ["método"]}, NOW)
    assert repo.get_matrix("p1") == {"dimensions": ["método"]}

    repo.delete_project("p1")
    assert repo.get_project("p1") is None and repo.list_items("p1") == [] and repo.get_matrix("p1") is None

    search = SavedSearch(search_id="s1", owner_id="ana", name="Recomendação", query="recomendação", filters={"year_from": 2020},
                         created_at=NOW, last_seen_at=NOW)
    repo.save_search(search)
    assert repo.list_searches("ana") == [search] and repo.list_searches("rui") == []

    feedback = SqlFeedbackRepository(repo.engine)
    feedback.add(AnswerFeedback(feedback_id="f1", user_id="ana", rating=-1, question="q", answer="a", created_at=NOW))
    feedback.add(AnswerFeedback(feedback_id="f2", user_id="ana", rating=1, question="q", answer="a", created_at="2026-11-04"))
    assert [f.feedback_id for f in feedback.list_recent()] == ["f2", "f1"]
    assert [f.feedback_id for f in feedback.list_recent(rating=-1)] == ["f1"]
    assert feedback.counts() == {1: 1, -1: 1}


# ---------------------------------------------------------------- funções puras


CARD = DocumentCard(
    document_id="d1",
    filename="2024 - Recomendação.pdf",
    title="Recomendação de Livros em Bibliotecas",
    year=2024,
    document_type="academic",
    authors=["Ana Rita Martins", "João da Silva"],
    keywords=["recomendação"],
    fields={"institution": "Universidade do Minho"},
)


def test_references_in_each_style():
    assert apa(CARD) == (
        "Martins, A. R., & Silva, J. (2024). Recomendação de Livros em Bibliotecas [Dissertação]. Universidade do Minho."
    )
    assert iso690(CARD) == (
        "MARTINS, Ana Rita; SILVA, João da. Recomendação de Livros em Bibliotecas. Dissertação, Universidade do Minho, 2024."
    )
    entry = bibtex(CARD)
    assert entry.startswith("@mastersthesis{martins2024recomendacao,")
    assert "author = {Ana Rita Martins and João da Silva}" in entry and "school = {Universidade do Minho}" in entry

    anonymous = DocumentCard(document_id="d2", filename="Manual interno.pdf", document_type="generic")
    assert apa(anonymous) == "Manual interno (s.d.)."
    later = CARD.model_copy(update={"document_id": "d3", "authors": ["Bruno Alves"]})
    assert bibliography([CARD, later], "apa")[0].startswith("Alves, B.")


def test_document_ids_scope_in_both_indexes():
    scope = SearchFilters(document_ids=["a", "b"])
    assert scope.to_where() == {"document_id": {"$in": ["a", "b"]}}
    assert scope.matches({"document_id": "a"}) and not scope.matches({"document_id": "c"})
    nothing = SearchFilters(document_ids=[])
    assert not nothing.is_empty() and not nothing.matches({"document_id": "a"})
    assert nothing.to_where() == {"document_id": {"$in": ["__nenhum__"]}}


def test_text_is_split_into_paragraphs_and_claims():
    text = "Curto.\n\nUm parágrafo que sozinho já tem caracteres suficientes para contar como parágrafo de análise, " \
           "com bastante contexto para a pesquisa.\n\nFim."
    paragraphs = split_paragraphs(text)
    assert len(paragraphs) == 1 and paragraphs[0].startswith("Curto. Um parágrafo") and paragraphs[0].endswith("Fim.")

    claims = split_claims("Os sistemas híbridos superam os colaborativos em bibliotecas. Sim. 70% dos leitores usam o catálogo online.")
    assert claims == ["Os sistemas híbridos superam os colaborativos em bibliotecas.", "70% dos leitores usam o catálogo online."]


def test_citations_are_checked_sentence_by_sentence():
    markdown = (
        "## Abordagens\n"
        "Os sistemas híbridos combinam conteúdo e colaboração [1]. "
        "Vários autores apontam limitações nos dados [2, 3]. "
        "Esta frase longa não tem qualquer fonte a apoiá-la."
    )
    assert check_citations(markdown, 2) == {
        "unsupported": ["Esta frase longa não tem qualquer fonte a apoiá-la."],
        "invalid_citations": [3],
    }


def test_kmeans_is_deterministic_and_separates_groups():
    vectors = np.array([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], dtype=float)
    labels = _kmeans(vectors, 2)
    assert labels == _kmeans(vectors, 2)
    assert labels[0] == labels[1] != labels[2] == labels[3]


# ---------------------------------------------------------------- fakes


class FakePipeline:
    """retrieve_sources devolve um excerto por documento que passe nos filtros, e regista os filtros pedidos."""

    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def retrieve_sources(self, question, top_k, document_id=None, retrieval_mode=None, filters=None):
        filters = filters or SearchFilters()
        self.calls.append(filters)
        sources = []
        for doc_id, filename in self.documents:
            meta = {"document_id": doc_id, "section": None}
            if filters.document_id and filters.document_id != doc_id:
                continue
            if filters.document_ids is not None and doc_id not in filters.document_ids:
                continue
            sources.append(SourceChunk(document_id=doc_id, filename=filename, page=2, chunk_index=0, score=0.8,
                                       text=f"Excerto de {filename} sobre {question[:30]}", section=meta["section"]))
        return sources[:top_k]

    # Usado pelo chat (modo RAG) no teste do âmbito do projeto.
    def ask(self, **kwargs):
        self.calls.append(kwargs.get("filters"))
        return "resposta", []


class FakeProfiles:
    def __init__(self, vectors: dict[str, list[float]], titles: dict[str, str]):
        self.vectors, self.titles = vectors, titles

    def query(self, embedding, top_k, where=None):
        allowed = None
        if where and "document_id" in where:
            allowed = set(where["document_id"]["$in"])
        ranked = sorted(self.vectors, key=lambda d: -float(np.dot(embedding, self.vectors[d])))
        return [
            {"metadata": {"document_id": d, "filename": f"{d}.pdf", "title": self.titles[d], "year": 2024},
             "text": self.titles[d], "score": 0.5}
            for d in ranked if allowed is None or d in allowed
        ][:top_k]

    def get_embeddings(self, ids):
        return {d: self.vectors[d] for d in ids if d in self.vectors}


class FakeLLM:
    def __init__(self, answers: dict):
        self.answers = answers

    def complete(self, messages, tools=None, tool_choice=None, temperature=0.2):
        name = tool_choice["function"]["name"]
        return {"tool_calls": [{"function": {"arguments": json.dumps(self.answers[name])}}]}

    def chat(self, system, user, temperature=0.2):
        return self.answers["chat"]


def _metadata(title, year, keywords, authors=(), references=()):
    return DocumentMetadata(document_type="academic", title=title, year=year, keywords=list(keywords), authors=list(authors),
                            references=list(references), fields={"advisors": ["Carlos Pinto"]})


@pytest.fixture
def base(tmp_path):
    """Base com três documentos indexados (dois sobre recomendação, um sobre redes) e um por rever."""
    engine = sql_engine("sqlite", tmp_path)
    registry, extractions = SqlDocumentRepository(engine), SqlExtractionRepository(engine)
    docs = {
        "rec1": ("Recomendação em bibliotecas", 2022, ["recomendação", "bibliotecas"], [1.0, 0.0, 0.0]),
        "rec2": ("Recomendação híbrida de livros", 2024, ["recomendação", "livros"], [0.95, 0.05, 0.0]),
        "net1": ("Redes de sensores", 2023, ["redes"], [0.0, 1.0, 0.0]),
    }
    for doc_id, (title, year, keywords, _) in docs.items():
        registry.add_or_replace(DocumentInfo(document_id=doc_id, filename=f"{doc_id}.pdf", sha256=doc_id, created_at=NOW,
                                             chunk_count=3, status="indexed", page_count=2, title=title, year=year))
        extractions.save_metadata(doc_id, _metadata(title, year, keywords, ["Ana Martins"], ["Silva (2020). Sistemas."]))
        extractions.save(doc_id, [ReviewPage(page=1, text="Capa", source="text"), ReviewPage(page=2, text=f"Texto de {title}.", source="text")])
    registry.add_or_replace(DocumentInfo(document_id="draft", filename="draft.pdf", sha256="x", created_at=NOW, chunk_count=0,
                                         status="pending_review"))
    profiles = FakeProfiles({d: v for d, (_, _, _, v) in docs.items()}, {d: t for d, (t, _, _, _) in docs.items()})
    pipeline = FakePipeline([(d, f"{d}.pdf") for d in docs])
    ctx = ToolContext(pipeline=pipeline, vector_store=None, registry=registry, export_store=ExportStore(tmp_path / "exports"),
                      extraction_store=extractions, document_types=TYPES, profile_store=profiles, embedding_model="fake")
    return {"engine": engine, "registry": registry, "extractions": extractions, "profiles": profiles, "pipeline": pipeline, "ctx": ctx}


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    """O tema "recomendação" fica perto dos documentos de recomendação; tudo o resto perto de redes."""

    def embed(model, text):
        return [1.0, 0.0, 0.0] if "recomenda" in text.lower() else [0.0, 1.0, 0.0]

    monkeypatch.setattr(discovery, "embed_query", embed)
    monkeypatch.setattr(research_api, "embed_query", embed)


def test_theme_map_groups_documents_and_counts_people(base):
    llm = FakeLLM({"name_groups": {"names": ["Recomendação", "Redes"]}})
    result = theme_map("recomendação de livros", SearchFilters(), 3, base["ctx"], llm)

    assert result["documents"] == 3
    groups = {c["label"]: {d["document_id"] for d in c["documents"]} for c in result["clusters"]}
    assert groups == {"Recomendação": {"rec1", "rec2"}, "Redes": {"net1"}}
    assert {"name": "Carlos Pinto", "role": "Orientadores", "count": 3} in result["people"]
    assert result["years"] == {2022: 1, 2023: 1, 2024: 1}
    assert result["references"] == [{"reference": "Silva (2020). Sistemas.", "cited_by": 3}]


def test_theme_map_without_llm_names_groups_by_keywords(base):
    result = theme_map("recomendação", SearchFilters(), 3, base["ctx"], None)
    assert sorted(c["label"] for c in result["clusters"])[0].startswith("recomendação")


def test_claims_get_verdicts_only_for_valid_answers(base):
    llm = FakeLLM({"record_verdicts": {"verdicts": [
        {"claim": 1, "verdict": "supported", "explanation": "O excerto diz isto.", "excerpts": [1]},
        {"claim": 2, "verdict": "inventado", "explanation": "", "excerpts": []},
        {"claim": 9, "verdict": "supported", "explanation": "", "excerpts": []},
    ]}})
    text = "A recomendação híbrida melhora as sugestões nas bibliotecas. As redes de sensores gastam pouca energia."
    claims = check_claims(text, SearchFilters(document_ids=["rec1"]), base["ctx"], llm)["claims"]

    assert [c["verdict"] for c in claims] == ["supported", "unchecked"]
    assert claims[0]["evidence"][0]["used"] is True
    # O âmbito (projeto) chega à pesquisa de cada afirmação.
    assert all(f.document_ids == ["rec1"] for f in base["pipeline"].calls)


def test_overlap_alert_for_a_very_similar_text(base):
    llm = FakeLLM({"record_difference": {"difference": "O teu trabalho foca-se em bibliotecas escolares."}})
    text = "Proponho um sistema de recomendação de livros para bibliotecas.\n\n" + "Mais contexto sobre o tema. " * 10
    result = discovery.analyze_text(text, SearchFilters(), base["ctx"], llm)

    assert [d["document_id"] for d in result["overlap"]] == ["rec1", "rec2"]
    assert result["overlap"][0]["level"] == "high" and result["overlap"][0]["difference"].startswith("O teu trabalho")
    assert result["paragraphs"] and result["paragraphs"][0]["excerpts"]


# ---------------------------------------------------------------- API


class _NoCredentials:
    def delete(self, scope, owner_id):
        return False


@pytest.fixture
def api(base, tmp_path, monkeypatch):
    users = SqlUserRepository(base["engine"])
    people = {name: AuthenticatedUser.of(create_local_user(users, name, "palavra-passe", ["chat"])) for name in ("ana", "rui", "eva")}
    repo = SqlResearchRepository(base["engine"])
    feedback = SqlFeedbackRepository(base["engine"])
    exports = ExportStore(tmp_path / "exports")
    settings = Settings(_env_file=None, upload_dir=str(tmp_path / "uploads"))
    llm = FakeLLM({})

    patches = {
        "get_research_repository": lambda: repo,
        "get_feedback_repository": lambda: feedback,
        "get_registry": lambda: base["registry"],
        "get_extraction_store": lambda: base["extractions"],
        "get_document_types": lambda: TYPES,
        "get_users": lambda: users,
        "get_export_store": lambda: exports,
        "get_utility_llm": lambda: llm,
        "get_lmstudio_client": lambda: llm,
        "get_settings": lambda: settings,
        "get_rag_pipeline": lambda: base["pipeline"],
        "llm_for": lambda *args, **kwargs: llm,
        "pipeline_for": lambda *args, **kwargs: base["pipeline"],
        "get_llm_credentials": lambda: _NoCredentials(),
        "research_context": lambda user, scope=None: ToolContext(**{**vars(base["ctx"]), "scope_document_ids": scope}),
    }
    for module in (access, research_api, projects_api, feedback_api, chat_api):
        for name, value in patches.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value)

    app = FastAPI()
    for module in (research_api, projects_api, feedback_api, chat_api):
        app.include_router(module.router)
    state = {"user": people["ana"], "people": people, "repo": repo, "llm": llm, "pipeline": base["pipeline"]}
    app.dependency_overrides[current_user] = lambda: state["user"]
    state["client"] = TestClient(app)
    return state


def _as(api, name):
    api["user"] = api["people"][name]
    return api["client"]


def test_project_access_by_role(api):
    client = _as(api, "ana")
    project = client.post("/research/projects", json={"title": "Recomendação", "question": "Como recomendar livros?"}).json()
    pid = project["project"]["project_id"]
    assert project["my_role"] == "owner"

    assert client.post(f"/research/projects/{pid}/documents/rec1").status_code == 200
    assert client.post(f"/research/projects/{pid}/documents/draft").status_code == 404  # ainda não indexado
    client.post(f"/research/projects/{pid}/members", json={"username": "rui", "role": "viewer"})
    client.post(f"/research/projects/{pid}/members", json={"username": "eva", "role": "editor"})

    # Quem não é membro nem sabe que o projeto existe.
    api["people"]["outro"] = AuthenticatedUser.of(api["people"]["ana"].user.model_copy(update={"user_id": "outro"}))
    assert _as(api, "outro").get(f"/research/projects/{pid}").status_code == 404

    viewer = _as(api, "rui")
    assert viewer.get(f"/research/projects/{pid}").json()["my_role"] == "viewer"
    assert viewer.post(f"/research/projects/{pid}/items", json={"text": "nota"}).status_code == 403
    assert viewer.post(f"/research/projects/{pid}/comments", json={"text": "Gosto deste tema"}).status_code == 200
    assert viewer.delete(f"/research/projects/{pid}").status_code == 403

    editor = _as(api, "eva")
    assert editor.post(f"/research/projects/{pid}/documents/rec2").status_code == 200
    assert editor.post(f"/research/projects/{pid}/members", json={"username": "rui", "role": "editor"}).status_code == 403
    assert [p["document_count"] for p in editor.get("/research/projects").json()] == [2]

    assert _as(api, "ana").delete(f"/research/projects/{pid}").status_code == 200
    assert api["repo"].list_members(pid) == []


def test_notebook_items_tags_search_and_comments(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P"}).json()["project"]["project_id"]
    excerpt = client.post(
        f"/research/projects/{pid}/items",
        json={"kind": "excerpt", "text": "Os sistemas híbridos são melhores.", "source": {"document_id": "rec1", "page": 2},
              "tags": ["Método ", "método", "dados"]},
    ).json()
    assert excerpt["tags"] == ["dados", "método"] and excerpt["author"] == "ana"
    client.post(f"/research/projects/{pid}/items", json={"kind": "note", "title": "Ideia", "text": "Falar com o orientador"})
    assert client.post(f"/research/projects/{pid}/items", json={"text": "  "}).status_code == 422

    assert [i["kind"] for i in client.get(f"/research/projects/{pid}/items", params={"q": "híbridos"}).json()] == ["excerpt"]
    assert [i["kind"] for i in client.get(f"/research/projects/{pid}/items", params={"tag": "dados"}).json()] == ["excerpt"]

    client.post(f"/research/projects/{pid}/comments", json={"text": "Ver p. 3", "item_id": excerpt["item_id"]})
    items = {i["kind"]: i for i in client.get(f"/research/projects/{pid}/items").json()}
    assert items["excerpt"]["comment_count"] == 1

    edited = client.patch(f"/research/projects/{pid}/items/{excerpt['item_id']}", json={"text": "Corrigido", "tags": ["x"]}).json()
    assert (edited["text"], edited["tags"]) == ("Corrigido", ["x"])
    assert client.delete(f"/research/projects/{pid}/items/{excerpt['item_id']}").status_code == 200


def test_comments_are_deleted_by_author_or_owner(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P"}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/members", json={"username": "rui", "role": "viewer"})
    client.post(f"/research/projects/{pid}/members", json={"username": "eva", "role": "editor"})
    comment = _as(api, "rui").post(f"/research/projects/{pid}/comments", json={"text": "Comentário"}).json()

    assert _as(api, "eva").delete(f"/research/projects/{pid}/comments/{comment['comment_id']}").status_code == 403
    assert _as(api, "ana").delete(f"/research/projects/{pid}/comments/{comment['comment_id']}").status_code == 200


def test_chat_and_search_are_limited_to_the_project(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P"}).json()["project"]["project_id"]
    assert client.post("/chat/ask", json={"question": "O que há?", "project_id": pid}).status_code == 400  # sem documentos
    client.post(f"/research/projects/{pid}/documents/rec2")

    assert client.post("/chat/ask", json={"question": "O que há?", "project_id": pid}).status_code == 200
    assert api["pipeline"].calls[-1].document_ids == ["rec2"]

    hits = client.post("/research/search", json={"query": "livros", "project_id": pid}).json()
    assert {h["document_id"] for h in hits} == {"rec2"} and hits[0]["title"] == "Recomendação híbrida de livros"
    everything = client.post("/research/search", json={"query": "livros"}).json()
    assert {h["document_id"] for h in everything} == {"rec1", "rec2", "net1"}

    # Projeto de outra pessoa: como se não existisse.
    assert _as(api, "rui").post("/chat/ask", json={"question": "O que há?", "project_id": pid}).status_code == 404


def test_search_rejects_unknown_filters_and_lists_facets(api):
    client = _as(api, "ana")
    assert client.post("/research/search", json={"query": "livros", "filters": {"document_type": "romance"}}).status_code == 422
    assert client.post("/research/search", json={"query": "livros", "filters": {"fields": {"cor": "azul"}}}).status_code == 422
    facets = client.get("/research/facets").json()
    assert facets["years"] == {"min": 2022, "max": 2024}
    assert {t["key"]: t["count"] for t in facets["types"]}["academic"] == 3


def test_saved_search_reports_new_documents(api, base):
    client = _as(api, "ana")
    search = client.post("/research/searches", json={"name": "Recomendação", "query": "recomendação", "filters": {"year_from": 2024}}).json()
    assert search["new_count"] == 0

    for doc_id, year in (("new1", 2025), ("old", 2010)):
        base["registry"].add_or_replace(DocumentInfo(document_id=doc_id, filename=f"{doc_id}.pdf", sha256=doc_id,
                                                     created_at="2099-01-01T00:00:00+00:00", chunk_count=1, status="indexed"))
        base["extractions"].save_metadata(doc_id, _metadata("Recomendação nova", year, []))
    base["profiles"].vectors.update(new1=[1.0, 0.0, 0.0], old=[1.0, 0.0, 0.0])
    base["profiles"].titles.update(new1="Recomendação nova", old="Antigo")

    [listed] = client.get("/research/searches").json()
    assert listed["new_count"] == 1
    assert [d["document_id"] for d in client.get(f"/research/searches/{search['search_id']}/new").json()] == ["new1"]
    # As pesquisas guardadas são de cada pessoa.
    assert _as(api, "rui").get(f"/research/searches/{search['search_id']}/new").status_code == 404


def test_reader_shows_only_indexed_documents(api):
    client = _as(api, "ana")
    page = client.get("/research/documents/rec1/pages/2").json()
    assert (page["text"], page["page_count"]) == ("Texto de Recomendação em bibliotecas.", 2)
    assert client.get("/research/documents/draft").status_code == 404
    assert client.get("/research/documents/rec1/pages/9").status_code == 404


def test_bibliography_and_export(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P"}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/documents/rec1")
    references = client.get(f"/research/projects/{pid}/bibliography", params={"style": "iso690"}).json()["references"]
    assert references == ["MARTINS, Ana. Recomendação em bibliotecas. Dissertação, 2022."]

    exported = client.post("/research/export", json={"title": "Bibliografia", "markdown": "\n".join(references), "format": "md"}).json()
    assert exported == {"name": "Bibliografia.md", "format": "md"}


def test_state_of_the_art_flags_unsupported_sentences(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P", "question": "Como recomendar livros?"}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/documents/rec1")
    api["llm"].answers["chat"] = "## Abordagens\nA recomendação em bibliotecas usa o histórico [1]. Esta afirmação longa não tem fonte nenhuma."

    result = client.post(f"/research/projects/{pid}/state-of-the-art", json={}).json()
    assert result["sources"][0]["n"] == 1 and result["sources"][0]["document_id"] == "rec1"
    assert result["unsupported"] == ["Esta afirmação longa não tem fonte nenhuma."]
    assert result["bibliography"] == ["Martins, A. (2022). Recomendação em bibliotecas [Dissertação]."]


def test_feedback_is_recorded_and_listed_for_admins(api):
    client = _as(api, "ana")
    res = client.post("/feedback", json={"rating": -1, "reason": " Fonte errada ", "question": "q", "answer": "a"})
    assert res.json()["reason"] == "Fonte errada"
    assert client.get("/feedback").status_code == 403

    api["user"] = AuthenticatedUser.of(api["people"]["ana"].user.model_copy(update={"roles": ["admin"]}))
    listed = api["client"].get("/feedback").json()
    assert (listed["negative"], listed["items"][0]["user"]) == (1, "ana")


def test_skeleton_follows_the_work_type_sections(api):
    api["llm"].answers["record_questions"] = {"sections": [{"key": "methodology", "questions": ["Que dados vais usar?"]}]}
    result = _as(api, "ana").post("/research/skeleton", json={"topic": "recomendação de livros", "work_type": "academic"}).json()

    keys = [s["key"] for s in result["sections"]]
    assert keys[0] == "abstract" and "methodology" in keys and "references" not in keys and "appendix" not in keys
    methodology = next(s for s in result["sections"] if s["key"] == "methodology")
    assert methodology["questions"] == ["Que dados vais usar?"] and methodology["relevant"]
    assert "## " in result["markdown"] and "- Que dados vais usar?" in result["markdown"]
    # Os exemplos vêm de trabalhos do mesmo tipo, na mesma secção.
    assert any(f.sections == ["methodology"] and f.document_type == "academic" for f in api["pipeline"].calls)


def test_matrix_is_filled_and_keeps_the_notes(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P"}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/documents/rec1")
    assert client.post(f"/research/projects/{pid}/matrix/fill", json={"dimensions": ["método"]}).status_code == 400
    client.post(f"/research/projects/{pid}/documents/rec2")

    api["llm"].answers["record_cells"] = {"cells": [{"document_id": "rec1", "dimension": "método", "summary": "Filtragem colaborativa."}]}
    matrix = client.post(f"/research/projects/{pid}/matrix/fill", json={"dimensions": ["método"]}).json()
    assert matrix["cells"]["rec1"]["método"]["summary"] == "Filtragem colaborativa."
    assert matrix["cells"]["rec2"]["método"]["excerpts"][0]["page"] == 2

    client.put(f"/research/projects/{pid}/matrix", json={"dimensions": ["método", "dados"], "notes": {"rec1": {"dados": "Empréstimos"}}})
    again = client.post(f"/research/projects/{pid}/matrix/fill", json={"dimensions": ["método", "dados"]}).json()
    assert again["notes"] == {"rec1": {"dados": "Empréstimos"}} and set(again["cells"]["rec2"]) == {"método", "dados"}


def test_gaps_suggestions_point_to_their_documents(api):
    api["llm"].answers["suggest_gaps"] = {"gaps": [
        {"title": "Recomendação em bibliotecas escolares", "description": "Ninguém estudou escolas.", "documents": [1]},
        {"title": "Sem apoio", "description": "", "documents": [99]},
    ]}
    result = _as(api, "ana").post("/research/gaps", json={"topic": "recomendação de livros"}).json()

    assert result["open_questions"]["documents"]
    [suggestion] = result["suggestions"]
    assert suggestion["title"] == "Recomendação em bibliotecas escolares" and suggestion["documents"][0]["document_id"]
    assert result["coverage"]["related_documents"] == 2


def test_draft_upload_is_analysed_without_being_stored(api):
    api["llm"].answers["record_difference"] = {"difference": "Muito parecido."}
    text = ("Proponho um sistema de recomendação de livros para bibliotecas municipais. " * 3).encode()
    res = _as(api, "ana").post("/research/text-analysis", files={"file": ("rascunho.txt", text, "text/plain")})

    assert res.status_code == 200, res.text
    assert res.json()["overlap"][0]["document_id"] == "rec1"
    assert api["client"].post("/research/text-analysis", files={"file": ("x.exe", b"MZ" * 40, "application/octet-stream")}).status_code == 400
    assert api["client"].post("/research/text-analysis", data={"text": "curto"}).status_code == 422


# ---------------------------------------------------------------- projeto a partir de uma conversa


CONVERSATION = [
    {"question": "Que regras há sobre o IVA?", "answer": "A taxa normal é 15% (p. 2).",
     "sources": [{"document_id": "rec1", "filename": "rec1.pdf", "page": 2, "text": "taxa"}]},
    {"question": "E prazos?", "answer": "A declaração é mensal.",
     "sources": [{"document_id": "rec2", "filename": "rec2.pdf", "page": 2}, {"document_id": "draft", "filename": "draft.pdf", "page": 1}]},
]


def test_conversation_draft_follows_whatever_structure_the_llm_proposes(api):
    api["llm"].answers["propose_project"] = {
        "title": "Plano X",
        "objective": "Organizar as regras",
        "sections": [{"title": "Regras", "ref_prefix": "r"}, {"title": "Dúvidas", "ref_prefix": ""}, {"title": "regras"}],
        "statuses": ["Proposto", "aprovado", "proposto"],
        "items": [
            {"section": "Regras", "title": "Taxa de IVA", "text": "15%", "sources": [1, 1, 99]},
            {"section": "regras", "title": "Prazo", "text": "Mensal", "sources": [2]},
            {"section": "Dúvidas", "title": "Isenções?", "text": "Por confirmar"},
            {"section": "Inexistente", "title": "Solta", "text": "Vai para a primeira secção"},
        ],
    }
    draft = _as(api, "ana").post("/research/projects/draft-from-conversation", json={"turns": CONVERSATION}).json()

    assert draft["generated"] and draft["title"] == "Plano X" and draft["question"] == "Organizar as regras"
    assert [s["key"] for s in draft["structure"]["sections"]] == ["regras", "duvidas"]
    assert draft["structure"]["statuses"] == ["proposto", "aprovado"]
    assert [(i["section"], i["ref"]) for i in draft["items"]] == [("regras", "R-001"), ("regras", "R-002"), ("duvidas", ""), ("regras", "R-003")]
    assert draft["items"][0]["sources"] == [{"document_id": "rec1", "filename": "rec1.pdf", "page": 2}]
    assert draft["items"][1]["sources"][0]["document_id"] == "rec2"
    assert draft["document_ids"] == ["rec1", "rec2"]  # "draft" ainda não está indexado


def test_conversation_draft_without_llm_keeps_the_conversation(api):
    draft = _as(api, "ana").post("/research/projects/draft-from-conversation", json={"turns": CONVERSATION}).json()
    assert not draft["generated"]
    assert [i["title"] for i in draft["items"]] == ["Que regras há sobre o IVA?", "E prazos?"]
    assert _as(api, "ana").post("/research/projects/draft-from-conversation", json={"turns": [{"question": " "}]}).status_code == 422


def test_project_is_created_from_the_reviewed_draft(api):
    structure = {"sections": [{"key": "regras", "title": "Regras", "description": ""}], "statuses": ["proposto", "aprovado"]}
    payload = {
        "title": "Plano X",
        "question": "Organizar as regras",
        "structure": structure,
        "items": [
            {"section": "regras", "ref": "R-001", "title": "Taxa", "text": "15%", "status": "proposto",
             "sources": [{"document_id": "rec1", "filename": "rec1.pdf", "page": 2}]},
            {"section": "regras", "ref": "R-002", "title": "Prazo", "text": "Mensal", "status": "proposto"},
        ],
        "document_ids": ["rec1", "draft"],
        "conversation": CONVERSATION,
        "members": [{"username": "rui", "role": "editor"}, {"username": "ninguem"}],
    }
    client = _as(api, "ana")
    bad = {**payload, "items": [{"section": "outra", "title": "x"}]}
    assert client.post("/research/projects/from-draft", json=bad).status_code == 422

    result = client.post("/research/projects/from-draft", json=payload).json()
    detail, pid = result["detail"], result["detail"]["project"]["project_id"]
    assert detail["project"]["structure"] == structure
    assert [d["document_id"] for d in detail["documents"]] == ["rec1"]
    assert {m["username"]: m["role"] for m in detail["members"]} == {"ana": "owner", "rui": "editor"}
    assert len(result["warnings"]) == 2

    items = client.get(f"/research/projects/{pid}/items").json()
    assert [(i["kind"], i["ref"]) for i in items] == [("note", "R-002"), ("note", "R-001"), ("answer", ""), ("answer", "")]
    assert items[1]["source"]["sources"][0]["page"] == 2
    assert [i["ref"] for i in client.get(f"/research/projects/{pid}/items", params={"section": "regras"}).json()] == ["R-002", "R-001"]

    editor = _as(api, "rui")
    item_id = items[0]["item_id"]
    assert editor.patch(f"/research/projects/{pid}/items/{item_id}", json={"status": "aprovado"}).json()["status"] == "aprovado"
    assert editor.patch(f"/research/projects/{pid}/items/{item_id}", json={"status": "fechado"}).status_code == 422
    renamed = editor.patch(f"/research/projects/{pid}", json={"structure": {**structure, "statuses": ["proposto", "aprovado", "fechado"]}})
    assert renamed.json()["project"]["structure"]["statuses"][-1] == "fechado"
    assert editor.patch(f"/research/projects/{pid}/items/{item_id}", json={"status": "fechado"}).status_code == 200


# ---------------------------------------------------------------- tools do caderno do projeto


def _workspace_context(api, base, can_edit=True):
    from backend.agent.tools.base import ProjectWorkspace

    client = _as(api, "ana")
    structure = {"sections": [{"key": "regras", "title": "Regras", "description": ""}, {"key": "duvidas", "title": "Dúvidas", "description": ""}],
                 "statuses": ["proposto", "aprovado"]}
    pid = client.post("/research/projects", json={"title": "P", "structure": structure}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/items", json={"title": "Taxa", "text": "15%", "section": "regras", "ref": "R-001", "status": "proposto"})
    client.post(f"/research/projects/{pid}/items", json={"title": "Isenções?", "section": "duvidas"})
    repo = api["repo"]
    workspace = ProjectWorkspace(project=repo.get_project(pid), repository=repo, can_edit=can_edit)
    return ToolContext(**{**vars(base["ctx"]), "workspace": workspace}), repo, pid


def test_project_tools_list_and_read_items(api, base):
    from backend.agent.tools.project import get_project_item, list_project_items

    ctx, _, _ = _workspace_context(api, base)
    listed = list_project_items.run({}, ctx).content
    assert [(i["ref"], i["section"]) for i in listed["items"]] == [("R-001", "Regras"), ("", "Dúvidas")]
    assert list_project_items.run({"section": "dúvidas"}, ctx).content["total"] == 1
    assert get_project_item.run({"item": "r-001"}, ctx).content["text"] == "15%"
    with pytest.raises(ToolError):
        get_project_item.run({"item": "R-999"}, ctx)
    with pytest.raises(ToolError):
        list_project_items.run({}, base["ctx"])  # fora de um projeto


def test_proposals_are_validated_and_never_written(api, base):
    from backend.agent.tools.project import propose_item_changes

    ctx, repo, pid = _workspace_context(api, base)
    result = propose_item_changes.run({"changes": [
        {"action": "create", "section": "Regras", "ref": "R-002", "title": "Prazo", "text": "Mensal [lei.pdf, p.3]"},
        {"action": "update", "item": "R-001", "status": "aprovado", "text": "15%", "reason": "confirmado"},
        {"action": "update", "item": "R-001", "text": "15%"},
        {"action": "create", "section": "Inexistente", "title": "x"},
    ]}, ctx)
    created, updated = result.proposals
    assert created["changes"] == {"section": "regras", "ref": "R-002", "title": "Prazo", "text": "Mensal [lei.pdf, p.3]", "status": "proposto"}
    assert updated["changes"] == {"status": "aprovado"} and updated["before"]["status"] == "proposto"
    assert len(result.content["errors"]) == 2
    assert repo.count_items(pid) == 2  # nada foi gravado
    with pytest.raises(ToolError):
        propose_item_changes.run({"changes": [{"action": "update", "item": "R-001", "status": "fechado"}]}, ctx)


def test_agent_prompt_describes_the_project_generically():
    from backend.api.agent import project_note

    project = Project(project_id="p", owner_id="a", title="Plano", question="Organizar regras", created_at=NOW, updated_at=NOW,
                      structure={"sections": [{"key": "regras", "title": "Regras"}], "statuses": ["proposto"]})
    note = project_note(project, document_count=2, item_count=5, can_edit=False)
    assert "Objetivo do projeto: Organizar regras" in note and "- regras: Regras" in note
    assert "propose_item_changes" in note and "só pode ler" in note


def test_proposals_carry_the_basis_of_their_content(api, base):
    from backend.agent.tools.project import propose_item_changes

    ctx, _, pid = _workspace_context(api, base)
    result = propose_item_changes.run({"changes": [
        {"action": "create", "section": "regras", "title": "Prazo", "text": "Mensal [lei.pdf, p.3]", "basis": "documents"},
        {"action": "create", "section": "duvidas", "title": "Ideia", "text": "E se fosse trimestral?"},
        {"action": "update", "item": "R-001", "status": "aprovado", "basis": "documents"},
        {"action": "create", "section": "regras", "title": "Sem fonte", "text": "Taxa de 20%", "basis": "documents"},
    ]}, ctx)
    cited, idea, status_only = result.proposals
    assert (cited["basis"], idea["basis"]) == ("documents", "assistant")  # por defeito: contributo do assistente
    assert "basis" not in status_only  # mudar só o estado não diz nada sobre a origem
    assert len(result.content["errors"]) == 1 and "citações" in result.content["errors"][0]

    # Aceite numa alteração, a origem fica no source da entrada, sem apagar o que lá estava.
    client = _as(api, "ana")
    item = client.post(f"/research/projects/{pid}/items", json={"title": "T", "source": {"origin": "chat", "question": "q"}}).json()
    updated = client.patch(f"/research/projects/{pid}/items/{item['item_id']}", json={"text": "novo", "basis": "mixed"}).json()
    assert updated["source"] == {"origin": "chat", "question": "q", "basis": "mixed"}
    # Proposta de um agente externo (MCP) aceite: o nome do token fica também no source.
    updated = client.patch(f"/research/projects/{pid}/items/{item['item_id']}", json={"text": "outro", "basis": "documents", "via": "Claude Code"}).json()
    assert updated["source"] == {"origin": "chat", "question": "q", "basis": "documents", "via": "Claude Code"}
    assert client.patch(f"/research/projects/{pid}/items/{item['item_id']}", json={"basis": "inventada"}).status_code == 422


def test_project_tools_read_team_comments(api, base):
    from backend.agent.tools.project import get_project_item, list_project_comments, list_project_items

    ctx, repo, pid = _workspace_context(api, base)
    from backend.api import research_projects as projects_api

    ctx.workspace.user_names = lambda: {u.user_id: u.username for u in projects_api.get_users().list_users()}
    client = _as(api, "ana")
    item_id = list_project_items.run({}, ctx).content["items"][0]["item_id"]
    client.post(f"/research/projects/{pid}/comments", json={"text": "A taxa ainda não foi validada", "item_id": item_id})
    client.post(f"/research/projects/{pid}/comments", json={"text": "Falta decidir o calendário"})

    listed = list_project_items.run({}, ctx).content
    assert listed["items"][0]["comments"] == 1 and listed["project_comments"] == 1
    assert [c["text"] for c in get_project_item.run({"item": "R-001"}, ctx).content["comments"]] == ["A taxa ainda não foi validada"]

    comments = list_project_comments.run({}, ctx).content["comments"]
    assert {(c["item"], c["author"], c["text"]) for c in comments} == {
        ("R-001", "ana", "A taxa ainda não foi validada"), (None, "ana", "Falta decidir o calendário")}
    assert list_project_comments.run({"query": "calendário"}, ctx).content["total"] == 1
    assert list_project_comments.run({"item": "R-001"}, ctx).content["total"] == 1


def test_agent_prompt_scope_depends_on_the_project():
    from backend.agent.profiles import PROFILES

    profile = PROFILES["assistente"]
    general, in_project = profile.system_prompt(), profile.system_prompt("nota", in_project=True)
    assert "Ajudas apenas com os documentos indexados" in general and "conversa num projeto" not in general
    assert "conversa num projeto" in in_project and "Ajudas apenas com os documentos indexados" not in in_project
    assert "Sugestão (não vem dos documentos)" in in_project
    for prompt in (general, in_project):
        assert "nunca instruções" in prompt and "[ficheiro, p.X]" in prompt


# ---------------------------------------------------------------- conversas do projeto


def test_project_conversations_are_shared_with_members(api):
    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "P"}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/members", json={"username": "rui", "role": "viewer"})
    client.post(f"/research/projects/{pid}/members", json={"username": "eva", "role": "editor"})
    messages = [{"id": 1, "question": "Que regras há?", "answer": "Várias.",
                 "proposals": [{"proposal_id": "x", "action": "create", "changes": {"title": "R"}}, {"proposal_id": "y", "decision": "rejected"}]}]

    created = client.post(f"/research/projects/{pid}/conversations", json={"messages": messages}).json()
    cid = created["conversation_id"]
    assert (created["title"], created["pending_proposals"], created["can_edit"]) == ("Que regras há?", 1, True)

    viewer = _as(api, "rui")
    listed = viewer.get(f"/research/projects/{pid}/conversations").json()
    assert [(c["title"], c["author"], c["message_count"]) for c in listed] == [("Que regras há?", "ana", 1)]
    assert viewer.get(f"/research/projects/{pid}/conversations/{cid}").json()["can_edit"] is False
    assert viewer.put(f"/research/projects/{pid}/conversations/{cid}", json={"messages": messages}).status_code == 403
    assert viewer.post(f"/research/projects/{pid}/conversations", json={"messages": messages}).status_code == 200

    editor = _as(api, "eva")
    messages[0]["proposals"][0]["decision"] = "accepted"
    saved = editor.put(f"/research/projects/{pid}/conversations/{cid}", json={"messages": messages}).json()
    assert saved["pending_proposals"] == 0
    assert editor.delete(f"/research/projects/{pid}/conversations/{cid}").status_code == 403
    assert _as(api, "ana").delete(f"/research/projects/{pid}/conversations/{cid}").status_code == 200

    outsider = AuthenticatedUser.of(api["people"]["ana"].user.model_copy(update={"user_id": "outro"}))
    api["people"]["outro"] = outsider
    assert _as(api, "outro").get(f"/research/projects/{pid}/conversations").status_code == 404


# ---------------------------------------------------------------- convites


@pytest.fixture
def invites(api, base, monkeypatch, tmp_path):
    import backend.api.invitations as invitations_api
    from backend.auth.authenticators import LocalAuthenticator

    settings = Settings(_env_file=None, upload_dir=str(tmp_path / "uploads"), auth_secret_key="x" * 40)
    users = SqlUserRepository(base["engine"])
    authenticator = LocalAuthenticator(users, "x" * 40, 60)
    for module in (invitations_api, projects_api):
        for name, value in {"get_research_repository": lambda: api["repo"], "get_users": lambda: users,
                            "get_settings": lambda: settings, "get_authenticator": lambda: authenticator}.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value)
    api["client"].app.include_router(invitations_api.router)
    api.update(settings=settings, authenticator=authenticator)
    return api


def test_invitation_by_email_adds_a_new_account_to_the_project(invites):
    client = _as(invites, "ana")
    pid = client.post("/research/projects", json={"title": "Plano"}).json()["project"]["project_id"]
    assert client.post(f"/research/projects/{pid}/invitations", json={"email": "nao-e-email"}).status_code == 422
    created = client.post(f"/research/projects/{pid}/invitations", json={"email": "Nova@Exemplo.pt", "role": "editor"}).json()
    token = created["token"]
    assert created["email"] == "nova@exemplo.pt"
    assert [i["email"] for i in client.get(f"/research/projects/{pid}/invitations").json()] == ["nova@exemplo.pt"]
    assert _as(invites, "rui").post(f"/research/projects/{pid}/invitations", json={"email": "a@b.pt"}).status_code == 404

    info = client.get(f"/invitations/{token}").json()
    assert (info["project_title"], info["invited_by"], info["status"], info["signup_allowed"]) == ("Plano", "ana", "pending", True)
    assert client.get("/invitations/token-falso").status_code == 404

    assert client.post(f"/invitations/{token}/signup", json={"username": "rui", "password": "palavra-passe"}).status_code == 409
    signed = client.post(f"/invitations/{token}/signup", json={"username": "nova", "password": "palavra-passe"}).json()
    assert signed["access_token"] and signed["user"]["user"]["roles"] == ["chat"]
    members = {m["username"]: m["role"] for m in _as(invites, "ana").get(f"/research/projects/{pid}").json()["members"]}
    assert members["nova"] == "editor"
    assert client.post(f"/invitations/{token}/signup", json={"username": "outra", "password": "palavra-passe"}).status_code == 410
    assert client.get(f"/research/projects/{pid}/invitations").json() == []


def test_invitation_is_accepted_by_an_existing_account_once(invites):
    client = _as(invites, "ana")
    pid = client.post("/research/projects", json={"title": "Plano"}).json()["project"]["project_id"]
    client.post(f"/research/projects/{pid}/members", json={"username": "rui", "role": "editor"})
    token = client.post(f"/research/projects/{pid}/invitations", json={"email": "rui@x.pt", "role": "viewer"}).json()["token"]
    other = client.post(f"/research/projects/{pid}/invitations", json={"email": "eva@x.pt"}).json()

    assert _as(invites, "rui").post(f"/invitations/{token}/accept").json() == {"project_id": pid}
    assert _as(invites, "rui").get(f"/research/projects/{pid}").json()["my_role"] == "editor"  # não baixa o papel
    assert _as(invites, "eva").post(f"/invitations/{token}/accept").status_code == 410

    client = _as(invites, "ana")
    assert client.delete(f"/research/projects/{pid}/invitations/{other['invitation_id']}").status_code == 200
    assert _as(invites, "eva").post(f"/invitations/{other['token']}/accept").status_code == 404

    invites["settings"].invite_signup_enabled = False
    client = _as(invites, "ana")
    token = client.post(f"/research/projects/{pid}/invitations", json={"email": "z@x.pt"}).json()["token"]
    assert client.get(f"/invitations/{token}").json()["signup_allowed"] is False
    assert client.post(f"/invitations/{token}/signup", json={"username": "zz", "password": "palavra-passe"}).status_code == 403


def test_agent_can_work_in_a_project_without_documents(api):
    from backend.api.agent import project_note

    client = _as(api, "ana")
    pid = client.post("/research/projects", json={"title": "Sem docs"}).json()["project"]["project_id"]
    assert access.project_scope(pid, api["user"], allow_empty=True) == []
    with pytest.raises(Exception):
        access.project_scope(pid, api["user"])  # a pesquisa normal continua a pedir documentos
    project = api["repo"].get_project(pid)
    assert "ainda não tem documentos" in project_note(project, document_count=0, item_count=0, can_edit=True)
