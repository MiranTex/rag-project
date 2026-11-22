"""Vetores numa tabela do PostgreSQL com a extensão pgvector, com a mesma interface do VectorStore (Chroma).

Usada quando a base de dados é PostgreSQL (VECTOR_STORE=pgvector): no Base Stack não há disco persistente
para o Chroma, e a base de dados já é um addon. As duas "coleções" do Chroma (excertos e índice de
documentos) são linhas da mesma tabela, separadas pela coluna collection.

Distância: as coleções do Chroma usam a predefinição (L2 ao quadrado) e o score é 1 / (1 + distância).
Os embeddings são normalizados (embed_texts/embed_query com normalize_embeddings=True), e para vetores de
norma 1 L2² = 2 × distância de cosseno. Aqui ordena-se pela distância de cosseno (<=>) e devolve-se
2 × essa distância, por isso a ordem e os scores são os mesmos que com o Chroma.
"""

import json
import time
from typing import Any

from sqlalchemy import Engine, text

TABLE = "vector_embeddings"

# Idempotente: corre na migração 0006 e de novo ao criar o store (se a extensão só foi instalada depois).
# A coluna não fixa a dimensão (vector e não vector(384)): mudar de EMBEDDING_MODEL não obriga a alterar o
# esquema, só a indexar de novo. A pesquisa é exata (sem índice HNSW), suficiente para alguns milhares de
# documentos.
SCHEMA_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        collection VARCHAR(128) NOT NULL,
        id TEXT NOT NULL,
        document_id TEXT,
        embedding vector NOT NULL,
        document TEXT NOT NULL DEFAULT '',
        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        PRIMARY KEY (collection, id)
    )""",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_document ON {TABLE} (collection, document_id)",
)

_COMPARISONS = {"$gt": ">", "$gte": ">=", "$lt": "<", "$lte": "<="}


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


class _Params:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def add(self, value: Any) -> str:
        name = f"w{len(self.values)}"
        self.values[name] = value
        return f":{name}"


def where_to_sql(where: dict | None, params: _Params) -> str:
    """Traduz um filtro `where` do Chroma (o que SearchFilters.to_chroma_where gera) para condições sobre a
    coluna metadata (JSONB). Operadores: igualdade, $eq, $ne, $in, $nin, $gt, $gte, $lt, $lte, $and, $or.

    Como no Chroma, uma comparação num campo que falta (ou de outro tipo) não passa no filtro."""
    if not where:
        return "TRUE"
    clauses = []
    for key, condition in where.items():
        if key in ("$and", "$or"):
            parts = [where_to_sql(item, params) for item in condition]
            joiner = " AND " if key == "$and" else " OR "
            clauses.append("(" + joiner.join(parts or ["TRUE" if key == "$and" else "FALSE"]) + ")")
            continue
        if not isinstance(condition, dict):
            condition = {"$eq": condition}
        for operator, value in condition.items():
            clauses.append(_condition(key, operator, value, params))
    return " AND ".join(clauses) if len(clauses) == 1 else "(" + " AND ".join(clauses) + ")"


def _condition(key: str, operator: str, value: Any, params: _Params) -> str:
    field = f"metadata -> {params.add(key)}"
    if operator == "$eq":
        # Contenção JSONB: compara também o tipo (2024 não é igual a "2024"), como o Chroma.
        return f"metadata @> CAST({params.add(json.dumps({key: value}))} AS jsonb)"
    if operator == "$ne":
        return f"({field} IS NOT NULL AND NOT metadata @> CAST({params.add(json.dumps({key: value}))} AS jsonb))"
    if operator in ("$in", "$nin"):
        # [valores] @> [campo]: o campo é um dos valores (um campo que falta dá [null] e não passa).
        contained = f"CAST({params.add(json.dumps(list(value)))} AS jsonb) @> jsonb_build_array({field})"
        return contained if operator == "$in" else f"({field} IS NOT NULL AND NOT {contained})"
    if operator in _COMPARISONS:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{operator} só aceita números (campo {key!r})")
        number = f"CASE WHEN jsonb_typeof({field}) = 'number' THEN ({field})::text::numeric END"
        return f"{number} {_COMPARISONS[operator]} CAST({params.add(value)} AS numeric)"
    raise ValueError(f"Operador de filtro não suportado: {operator}")


class PgVectorStore:
    def __init__(self, engine: Engine, collection_name: str, ensure_schema: bool = True) -> None:
        self.engine = engine
        self.collection_name = collection_name
        if ensure_schema:
            with engine.begin() as conn:
                exists = conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": TABLE}).scalar()
                if not exists:
                    for statement in SCHEMA_STATEMENTS:
                        conn.execute(text(statement))

    def heartbeat(self) -> int:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return time.time_ns()

    def upsert_chunks(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        rows = [
            {
                "c": self.collection_name,
                "id": item_id,
                "doc": (meta or {}).get("document_id"),
                "e": _vector_literal(vector),
                "t": document or "",
                "m": json.dumps(meta or {}, ensure_ascii=False),
            }
            for item_id, vector, document, meta in zip(ids, embeddings, documents, metadatas, strict=True)
        ]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""INSERT INTO {TABLE} (collection, id, document_id, embedding, document, metadata)
                    VALUES (:c, :id, :doc, CAST(:e AS vector), :t, CAST(:m AS jsonb))
                    ON CONFLICT (collection, id) DO UPDATE SET document_id = EXCLUDED.document_id,
                        embedding = EXCLUDED.embedding, document = EXCLUDED.document, metadata = EXCLUDED.metadata"""
                ),
                rows,
            )

    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        if not ids:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT id, embedding::text FROM {TABLE} WHERE collection = :c AND id = ANY(:ids)"),
                {"c": self.collection_name, "ids": list(ids)},
            ).all()
        return {row[0]: [float(v) for v in json.loads(row[1])] for row in rows}

    def list_ids(self) -> set[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"SELECT id FROM {TABLE} WHERE collection = :c"), {"c": self.collection_name})
            return {row[0] for row in rows}

    def update_document_metadata(self, document_id: str, updates: dict) -> int:
        """Altera campos dos metadados de todas as entradas de um documento (ex.: o nome); devolve quantas."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    f"""UPDATE {TABLE} SET metadata = metadata || CAST(:u AS jsonb)
                    WHERE collection = :c AND document_id = :d"""
                ),
                {"c": self.collection_name, "d": document_id, "u": json.dumps(updates, ensure_ascii=False)},
            )
            return result.rowcount

    def delete_document(self, document_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {TABLE} WHERE collection = :c AND document_id = :d"),
                {"c": self.collection_name, "d": document_id},
            )

    def list_chunks(self, document_id: str | None = None) -> list[dict]:
        sql = f"SELECT document, metadata FROM {TABLE} WHERE collection = :c"
        values: dict[str, Any] = {"c": self.collection_name}
        if document_id:
            sql += " AND document_id = :d"
            values["d"] = document_id
        # Ordem estável (o Chroma devolve pela ordem de inserção): documento e posição do excerto.
        sql += " ORDER BY document_id, CASE WHEN jsonb_typeof(metadata -> 'chunk_index') = 'number' THEN (metadata ->> 'chunk_index')::numeric END, id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), values).all()
        return [{"text": row[0], "metadata": row[1]} for row in rows]

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        document_id: str | None = None,
        where: dict | None = None,
    ) -> list[dict]:
        """`where` (filtro do Chroma, ver SearchFilters.to_chroma_where) tem prioridade sobre document_id."""
        where = where or ({"document_id": document_id} if document_id else None)
        params = _Params()
        condition = where_to_sql(where, params)
        sql = f"""SELECT document, metadata, embedding <=> CAST(:q AS vector) AS distance FROM {TABLE}
            WHERE collection = :c AND {condition} ORDER BY distance LIMIT :k"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(sql),
                {**params.values, "c": self.collection_name, "q": _vector_literal(query_embedding), "k": int(top_k)},
            ).all()
        # 2 × distância de cosseno = L2² para vetores normalizados: o mesmo score que com o Chroma.
        return [{"text": row[0], "metadata": row[1], "score": 1.0 / (1.0 + 2.0 * float(row[2]))} for row in rows]
