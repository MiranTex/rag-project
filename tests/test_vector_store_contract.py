"""Contrato do armazenamento de vetores (pgvector), incluindo os filtros `where` que a aplicação gera
(SearchFilters.to_where) e os scores.

Precisa de um PostgreSQL com a extensão (ex.: imagem pgvector/pgvector:0.8.7-pg17-trixie) em TEST_DATABASE_URL;
sem ela, ou sem a extensão no servidor, os testes ficam por correr (skip):

    docker run -d --name rag-pgvector-test -e POSTGRES_PASSWORD=rag -p 55432:5432 pgvector/pgvector:0.8.7-pg17-trixie
    TEST_DATABASE_URL=postgresql+psycopg://postgres:rag@localhost:55432/postgres pytest tests/test_vector_store_contract.py
"""

import math
import os
import uuid

import pytest
from sqlalchemy import text

from backend.repositories.database import upgrade_database
from backend.repositories.sql import create_db_engine
from backend.services.search_filters import SearchFilters
from backend.services.vector_store import TABLE, VectorStore


def _pg_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    upgrade_database(url)
    engine = create_db_engine(url)
    with engine.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar():
            pytest.skip("extensão pgvector não instalada no PostgreSQL de testes")
    return engine


@pytest.fixture
def make_store():
    """Fábrica de stores; cada nome é uma coleção nova (o PostgreSQL de testes é partilhado entre testes)."""
    suffix = uuid.uuid4().hex[:8]
    engine = _pg_engine()
    yield lambda name="chunks": VectorStore(engine, f"{name}_{suffix}")
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {TABLE} WHERE collection LIKE :c"), {"c": f"%_{suffix}"})


def _unit(*values: float) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


CHUNKS = [
    # id, vetor, texto, metadados
    ("d1:0", _unit(1, 0, 0), "Introdução ao contrato.", {"document_id": "d1", "chunk_index": 0, "section": "intro", "year": 2020, "document_type": "contract", "course": "Direito"}),
    ("d1:1", _unit(1, 1, 0), "Cláusulas de retribuição.", {"document_id": "d1", "chunk_index": 1, "section": "body", "year": 2020, "document_type": "contract", "course": "Direito"}),
    ("d2:0", _unit(0, 1, 0), "Resumo da tese.", {"document_id": "d2", "chunk_index": 0, "section": "abstract", "year": 2024, "document_type": "academic", "course": "Informática"}),
    ("d3:0", _unit(0, 0, 1), "Manual sem ano.", {"document_id": "d3", "chunk_index": 0, "section": "body", "document_type": "generic"}),
]


@pytest.fixture
def store(make_store):
    store = make_store()
    store.upsert_chunks(
        ids=[c[0] for c in CHUNKS],
        embeddings=[c[1] for c in CHUNKS],
        documents=[c[2] for c in CHUNKS],
        metadatas=[c[3] for c in CHUNKS],
    )
    return store


def _ids(results: list[dict]) -> list[str]:
    return [f"{r['metadata']['document_id']}:{r['metadata']['chunk_index']}" for r in results]


def test_heartbeat(make_store):
    assert make_store().heartbeat()


def test_list_chunks_and_ids(store):
    assert store.list_ids() == {"d1:0", "d1:1", "d2:0", "d3:0"}
    chunks = store.list_chunks("d1")
    assert [c["text"] for c in chunks] == ["Introdução ao contrato.", "Cláusulas de retribuição."]
    assert chunks[1]["metadata"] == CHUNKS[1][3]
    assert len(store.list_chunks()) == 4
    assert store.list_chunks("nope") == []


def test_upsert_replaces_by_id(store):
    store.upsert_chunks(["d2:0"], [_unit(0, 1, 1)], ["Resumo novo."], [{**CHUNKS[2][3], "year": 2025}])
    chunk = store.list_chunks("d2")
    assert [(c["text"], c["metadata"]["year"]) for c in chunk] == [("Resumo novo.", 2025)]
    assert len(store.list_ids()) == 4


def test_get_embeddings(store):
    vectors = store.get_embeddings(["d1:1", "d2:0", "nope"])
    assert set(vectors) == {"d1:1", "d2:0"}
    assert vectors["d1:1"] == pytest.approx(_unit(1, 1, 0), abs=1e-6)


def test_update_document_metadata_merges(store):
    assert store.update_document_metadata("d1", {"filename": "Contrato.pdf"}) == 2
    assert store.update_document_metadata("nope", {"filename": "x"}) == 0
    metas = [c["metadata"] for c in store.list_chunks("d1")]
    assert all(m["filename"] == "Contrato.pdf" and m["document_id"] == "d1" for m in metas)
    assert "filename" not in store.list_chunks("d2")[0]["metadata"]


def test_delete_document(store):
    store.delete_document("d1")
    assert store.list_ids() == {"d2:0", "d3:0"}


def test_collections_are_separate(make_store, store):
    profiles = make_store("profiles")
    profiles.upsert_chunks(["d1"], [_unit(1, 0, 0)], ["Ficha"], [{"document_id": "d1"}])
    assert profiles.list_ids() == {"d1"}
    profiles.delete_document("d1")
    assert len(store.list_chunks("d1")) == 2


def test_query_orders_by_similarity_with_l2_scores(store):
    query = _unit(1, 0.2, 0)
    results = store.query(query, top_k=3)
    assert _ids(results) == ["d1:0", "d1:1", "d2:0"]
    # Score: 1 / (1 + L2²).
    for result, chunk in zip(results, [CHUNKS[0], CHUNKS[1], CHUNKS[2]], strict=True):
        squared = sum((a - b) ** 2 for a, b in zip(query, chunk[1], strict=True))
        assert result["score"] == pytest.approx(1 / (1 + squared), abs=1e-5)
    assert results[0]["text"] == "Introdução ao contrato." and results[0]["metadata"] == CHUNKS[0][3]


def test_query_by_document_id(store):
    assert _ids(store.query(_unit(0, 1, 0), top_k=5, document_id="d1")) == ["d1:1", "d1:0"]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (SearchFilters(document_id="d2"), {"d2:0"}),
        (SearchFilters(document_ids=["d1", "d3"]), {"d1:0", "d1:1", "d3:0"}),
        (SearchFilters(document_ids=[]), set()),
        (SearchFilters(document_type="academic"), {"d2:0"}),
        # Sem ano não passa num filtro de ano.
        (SearchFilters(year_from=2021), {"d2:0"}),
        (SearchFilters(year_to=2020), {"d1:0", "d1:1"}),
        (SearchFilters(year_from=2020, year_to=2024), {"d1:0", "d1:1", "d2:0"}),
        (SearchFilters(sections=["intro", "abstract"]), {"d1:0", "d2:0"}),
        (SearchFilters(fields={"course": "Direito"}), {"d1:0", "d1:1"}),
        (SearchFilters(document_ids=["d1", "d2"], sections=["body"], year_from=2019), {"d1:1"}),
        (SearchFilters(document_type="contract", fields={"course": "Informática"}), set()),
    ],
)
def test_query_where_filters(store, filters, expected):
    results = store.query(_unit(1, 1, 1), top_k=10, where=filters.to_where())
    assert set(_ids(results)) == expected


def test_query_where_types_must_match(store):
    # Igualdade com tipo: o ano 2020 (número) não é "2020" (texto).
    assert store.query(_unit(1, 1, 1), top_k=10, where={"year": "2020"}) == []
    assert set(_ids(store.query(_unit(1, 1, 1), top_k=10, where={"year": 2020}))) == {"d1:0", "d1:1"}
