from types import SimpleNamespace

import pytest

from backend.agent.tools import ToolContext, ToolError, build_registry
from backend.models import DocumentMetadata, SourceChunk
from backend.services.document_types import load_document_types
from backend.services.extraction_review import ExtractionStore
from backend.services.keyword_index import KeywordIndex
from backend.services.search_filters import SearchFilters

TYPES = load_document_types("backend/document_types.json")


def test_filters_build_chroma_where_and_match_metadata():
    filters = SearchFilters(document_type="academic", year_from=2020, sections=["conclusion"], fields={"course": "EI"})

    assert filters.to_chroma_where() == {
        "$and": [
            {"document_type": "academic"},
            {"year": {"$gte": 2020}},
            {"section": {"$in": ["conclusion"]}},
            {"course": "EI"},
        ]
    }
    meta = {"document_type": "academic", "year": 2022, "section": "conclusion", "course": "EI"}
    assert filters.matches(meta)
    assert not filters.matches({**meta, "year": 2019})
    assert not filters.matches({**meta, "section": "introduction"})
    # Documentos sem ano não passam num filtro de ano.
    assert not filters.matches({k: v for k, v in meta.items() if k != "year"})
    assert SearchFilters(document_id="d1").to_chroma_where() == {"document_id": "d1"}
    assert SearchFilters().to_chroma_where() is None


def test_keyword_index_applies_predicate():
    index = KeywordIndex()
    index.index_document("a", [{"text": "trabalho futuro integrar catálogo", "metadata": _meta("a", 0, "future_work")}])
    index.index_document("b", [{"text": "integrar catálogo nacional", "metadata": _meta("b", 0, "introduction")}])

    results = index.search("integrar catálogo", top_k=5, predicate=SearchFilters(sections=["future_work"]).matches)

    assert [r["metadata"]["document_id"] for r in results] == ["a"]


def _meta(document_id, chunk_index, section, page=1):
    return {"document_id": document_id, "filename": f"{document_id}.pdf", "page": page, "chunk_index": chunk_index, "section": section}


class _FakePipeline:
    def __init__(self):
        self.calls = []

    def retrieve_sources(self, question, top_k, filters=None, **kwargs):
        self.calls.append(filters)
        return [
            SourceChunk(document_id="a", filename="a.pdf", page=9, chunk_index=3, score=0.8, text="Integrar…", section="future_work")
        ]


class _FakeVectorStore:
    def __init__(self, chunks):
        self.chunks = chunks

    def list_chunks(self, document_id=None):
        return [c for c in self.chunks if c["metadata"]["document_id"] == document_id]


class _FakeProfileStore:
    def __init__(self):
        self.queries = []

    def get_embeddings(self, ids):
        return {i: [0.1] for i in ids if i == "a"}

    def query(self, query_embedding, top_k, where=None):
        self.queries.append((top_k, where))
        return [
            {"text": "Recomendação de livros", "score": 1.0, "metadata": {"document_id": "a", "title": "A", "year": 2024}},
            {"text": "Sistemas de recomendação", "score": 0.7, "metadata": {"document_id": "b", "title": "B", "year": 2021}},
        ]


class _FakeRegistry:
    def __init__(self):
        self.docs = {
            "a": SimpleNamespace(document_id="a", filename="a.pdf", chunk_count=3, status="indexed"),
            "p": SimpleNamespace(document_id="p", filename="p.pdf", chunk_count=0, status="pending_review"),
        }

    def find_by_id(self, document_id):
        return self.docs.get(document_id)

    def list_documents(self):
        return list(self.docs.values())


@pytest.fixture
def ctx(tmp_path):
    store = ExtractionStore(str(tmp_path))
    store.save_metadata(
        "a",
        DocumentMetadata(
            document_type="academic",
            title="Recomendação de livros",
            year=2024,
            keywords=["recomendação"],
            fields={"course": "Engenharia Informática", "advisors": ["João Silva"]},
            references=["Silva (2020)", "Ricci (2015)"],
        ),
    )
    chunks = [
        {"text": "Capa", "metadata": _meta("a", 0, "front_matter", 1)},
        {"text": "Os leitores…", "metadata": _meta("a", 1, "introduction", 4)},
        {"text": "Conclui-se…", "metadata": _meta("a", 2, "conclusion", 9)},
        {"text": "Integrar…", "metadata": _meta("a", 3, "future_work", 9)},
        {"text": "Mais conclusões…", "metadata": _meta("a", 4, "conclusion", 10)},
    ]
    return ToolContext(
        pipeline=_FakePipeline(),
        vector_store=_FakeVectorStore(chunks),
        registry=_FakeRegistry(),
        export_store=None,
        extraction_store=store,
        document_types=TYPES,
        profile_store=_FakeProfileStore(),
        embedding_model="fake",
    )


def run(ctx, name, **arguments):
    return build_registry().get(name).run(arguments, ctx)


def test_list_documents_shows_profile_and_available_filters(ctx):
    content = run(ctx, "list_documents").content

    assert content["documents"] == [
        {
            "document_id": "a",
            "filename": "a.pdf",
            "chunk_count": 3,
            "document_type": "academic",
            "title": "Recomendação de livros",
            "year": 2024,
            # Só os campos filtráveis; orientadores ficam de fora.
            "course": "Engenharia Informática",
        }
    ]
    academic = content["document_types"]["academic"]
    assert "future_work" in academic["sections"] and "chapter" in academic["sections"]
    assert academic["filter_fields"] == ["course", "institution"]


def test_search_documents_passes_filters_and_reports_section(ctx):
    result = run(ctx, "search_documents", query="o que ficou por fazer", sections=["future_work"], year_from=2020)

    filters = ctx.pipeline.calls[0]
    assert filters.sections == ["future_work"] and filters.year_from == 2020
    assert result.content[0]["section"] == "future_work"


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"sections": ["conclusoes"]}, "Secções desconhecidas"),
        ({"document_type": "receita"}, "Tipo desconhecido"),
        ({"fields": {"advisors": "João"}}, "Campos não filtráveis"),
    ],
)
def test_search_documents_rejects_unknown_filter_keys(ctx, arguments, message):
    with pytest.raises(ToolError, match=message):
        run(ctx, "search_documents", query="x", **arguments)


def test_read_document_by_section(ctx):
    content = run(ctx, "read_document", document_id="a", section="conclusion").content

    assert [p["page"] for p in content["pages"]] == [9, 10]
    assert "Integrar" not in content["pages"][0]["text"]


def test_document_overview_lists_sections_with_pages(ctx):
    content = run(ctx, "get_document_overview", document_id="a").content

    assert content["document_type"] == "Trabalho académico"
    assert content["fields"] == {"Curso": "Engenharia Informática", "Orientadores": ["João Silva"]}
    assert content["references"] == 2
    assert content["sections"] == [
        {"section": "front_matter", "label": "Elementos iniciais", "pages": "1", "excerpts": 1},
        {"section": "introduction", "label": "Introdução", "pages": "4", "excerpts": 1},
        {"section": "conclusion", "label": "Conclusões", "pages": "9–10", "excerpts": 2},
        {"section": "future_work", "label": "Trabalho futuro", "pages": "9", "excerpts": 1},
    ]
    with pytest.raises(ToolError):
        run(ctx, "get_document_overview", document_id="p")


def test_find_similar_documents_by_document_excludes_itself(ctx):
    result = run(ctx, "find_similar_documents", document_id="a", top_k=1, year_from=2020)

    assert [d["document_id"] for d in result.content] == ["b"]
    # Pede mais um resultado para compensar o próprio documento.
    assert ctx.profile_store.queries[0] == (2, {"year": {"$gte": 2020}})


def test_find_similar_documents_needs_query_or_document(ctx):
    with pytest.raises(ToolError, match="query"):
        run(ctx, "find_similar_documents")
    with pytest.raises(ToolError, match="sem ficha"):
        run(ctx, "find_similar_documents", document_id="zzz")
