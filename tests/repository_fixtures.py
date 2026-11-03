"""Bases de dados para os testes de contrato: SQLite sempre; PostgreSQL se TEST_DATABASE_URL estiver definida
(ex.: postgresql+psycopg://rag:rag@localhost:5432/rag_test)."""

import os

import pytest
from sqlalchemy import delete

from backend.repositories.database import upgrade_database
import backend.repositories.research_sql  # noqa: F401  (tabelas da área de pesquisa no metadata_obj)
from backend.repositories.sql import create_db_engine, metadata_obj

SQL_BACKENDS = ["sqlite", "postgres"]


def sql_engine(kind: str, tmp_path):
    if kind == "sqlite":
        url = f"sqlite:///{tmp_path}/contract.db"
    else:
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL não definida")
    upgrade_database(url)
    engine = create_db_engine(url)
    # PostgreSQL é partilhado entre testes: cada teste começa com as tabelas vazias.
    with engine.begin() as conn:
        for table in reversed(metadata_obj.sorted_tables):
            conn.execute(delete(table))
    return engine
