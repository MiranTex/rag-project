"""Implementação SQL dos repositórios da área de pesquisa (mesmas tabelas em SQLite e PostgreSQL)."""

from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Engine,
    Integer,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)

from backend.repositories.sql import metadata_obj
from backend.research.models import (
    AnswerFeedback,
    Comment,
    NotebookItem,
    Project,
    ProjectDocument,
    ProjectMember,
    SavedSearch,
)

projects = Table(
    "projects",
    metadata_obj,
    Column("project_id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("title", String(200), nullable=False),
    Column("question", Text, nullable=False, default=""),
    Column("description", Text, nullable=False, default=""),
    Column("work_type", String(64), nullable=False, default=""),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

project_members = Table(
    "project_members",
    metadata_obj,
    Column("project_id", String(64), primary_key=True),
    Column("user_id", String(64), primary_key=True, index=True),
    Column("role", String(16), nullable=False),
)

project_documents = Table(
    "project_documents",
    metadata_obj,
    Column("project_id", String(64), primary_key=True),
    Column("document_id", String(64), primary_key=True),
    Column("added_by", String(64), nullable=False),
    Column("added_at", String(40), nullable=False),
)

notebook_items = Table(
    "notebook_items",
    metadata_obj,
    Column("item_id", String(64), primary_key=True),
    Column("project_id", String(64), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("title", String(300), nullable=False, default=""),
    Column("text", Text, nullable=False, default=""),
    Column("source", JSON, nullable=False),
    Column("tags", JSON, nullable=False),
    Column("created_by", String(64), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

project_comments = Table(
    "project_comments",
    metadata_obj,
    Column("comment_id", String(64), primary_key=True),
    Column("project_id", String(64), nullable=False, index=True),
    Column("item_id", String(64), nullable=True),
    Column("author_id", String(64), nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

project_matrices = Table(
    "project_matrices",
    metadata_obj,
    Column("project_id", String(64), primary_key=True),
    Column("data", JSON, nullable=False),
    Column("updated_at", String(40), nullable=False),
)

saved_searches = Table(
    "saved_searches",
    metadata_obj,
    Column("search_id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("query", Text, nullable=False),
    Column("filters", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False),
)

answer_feedback = Table(
    "answer_feedback",
    metadata_obj,
    Column("feedback_id", String(64), primary_key=True),
    Column("user_id", String(64), nullable=False),
    Column("rating", Integer, nullable=False),
    Column("reason", Text, nullable=False, default=""),
    Column("question", Text, nullable=False),
    Column("answer", Text, nullable=False),
    Column("mode", String(16), nullable=False),
    Column("sources", JSON, nullable=False),
    Column("project_id", String(64), nullable=True),
    Column("created_at", String(40), nullable=False),
)

# Ao apagar um projeto, sai tudo o que lhe pertence.
_PROJECT_CHILDREN = (project_members, project_documents, notebook_items, project_comments, project_matrices)


def _upsert(conn, table: Table, key: dict[str, Any], values: dict[str, Any]) -> None:
    condition = and_(*(table.c[name] == value for name, value in key.items()))
    if conn.execute(update(table).where(condition).values(**values)).rowcount == 0:
        conn.execute(insert(table).values(**key, **values))


class SqlResearchRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _one(self, table: Table, condition, model):
        with self.engine.connect() as conn:
            row = conn.execute(select(table).where(condition)).first()
        return model(**row._mapping) if row else None

    def _all(self, statement, model) -> list:
        with self.engine.connect() as conn:
            return [model(**row._mapping) for row in conn.execute(statement)]

    # ---- Projetos ----

    def save_project(self, project: Project) -> None:
        values = project.model_dump()
        with self.engine.begin() as conn:
            _upsert(conn, projects, {"project_id": values.pop("project_id")}, values)

    def get_project(self, project_id: str) -> Project | None:
        return self._one(projects, projects.c.project_id == project_id, Project)

    def list_projects_for(self, user_id: str) -> list[Project]:
        """Projetos de que é dono ou membro, os alterados mais recentemente primeiro."""
        member_of = select(project_members.c.project_id).where(project_members.c.user_id == user_id)
        statement = (
            select(projects)
            .where(or_(projects.c.owner_id == user_id, projects.c.project_id.in_(member_of)))
            .order_by(projects.c.updated_at.desc())
        )
        return self._all(statement, Project)

    def delete_project(self, project_id: str) -> None:
        with self.engine.begin() as conn:
            for table in _PROJECT_CHILDREN:
                conn.execute(delete(table).where(table.c.project_id == project_id))
            conn.execute(delete(projects).where(projects.c.project_id == project_id))

    # ---- Membros ----

    def list_members(self, project_id: str) -> list[ProjectMember]:
        return self._all(select(project_members).where(project_members.c.project_id == project_id), ProjectMember)

    def set_member(self, member: ProjectMember) -> None:
        with self.engine.begin() as conn:
            _upsert(conn, project_members, {"project_id": member.project_id, "user_id": member.user_id}, {"role": member.role})

    def remove_member(self, project_id: str, user_id: str) -> bool:
        with self.engine.begin() as conn:
            condition = and_(project_members.c.project_id == project_id, project_members.c.user_id == user_id)
            return conn.execute(delete(project_members).where(condition)).rowcount > 0

    # ---- Documentos fixados ----

    def list_project_documents(self, project_id: str) -> list[ProjectDocument]:
        statement = (
            select(project_documents)
            .where(project_documents.c.project_id == project_id)
            .order_by(project_documents.c.added_at, project_documents.c.document_id)
        )
        return self._all(statement, ProjectDocument)

    def add_project_document(self, document: ProjectDocument) -> None:
        with self.engine.begin() as conn:
            key = {"project_id": document.project_id, "document_id": document.document_id}
            _upsert(conn, project_documents, key, {"added_by": document.added_by, "added_at": document.added_at})

    def remove_project_document(self, project_id: str, document_id: str) -> bool:
        with self.engine.begin() as conn:
            condition = and_(project_documents.c.project_id == project_id, project_documents.c.document_id == document_id)
            return conn.execute(delete(project_documents).where(condition)).rowcount > 0

    # ---- Caderno ----

    def save_item(self, item: NotebookItem) -> None:
        values = item.model_dump(mode="json")
        with self.engine.begin() as conn:
            _upsert(conn, notebook_items, {"item_id": values.pop("item_id")}, values)

    def get_item(self, item_id: str) -> NotebookItem | None:
        return self._one(notebook_items, notebook_items.c.item_id == item_id, NotebookItem)

    def list_items(self, project_id: str, kind: str | None = None, query: str | None = None) -> list[NotebookItem]:
        """Mais recentes primeiro; `query` procura (sem distinguir maiúsculas) no título e no texto."""
        conditions = [notebook_items.c.project_id == project_id]
        if kind:
            conditions.append(notebook_items.c.kind == kind)
        if query:
            pattern = f"%{query.lower()}%"
            conditions.append(or_(func.lower(notebook_items.c.title).like(pattern), func.lower(notebook_items.c.text).like(pattern)))
        statement = select(notebook_items).where(*conditions).order_by(notebook_items.c.created_at.desc())
        return self._all(statement, NotebookItem)

    def delete_item(self, item_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(project_comments).where(project_comments.c.item_id == item_id))
            conn.execute(delete(notebook_items).where(notebook_items.c.item_id == item_id))

    def count_items(self, project_id: str) -> int:
        with self.engine.connect() as conn:
            return conn.execute(
                select(func.count()).select_from(notebook_items).where(notebook_items.c.project_id == project_id)
            ).scalar_one()

    # ---- Comentários ----

    def add_comment(self, comment: Comment) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(project_comments).values(**comment.model_dump()))

    def get_comment(self, comment_id: str) -> Comment | None:
        return self._one(project_comments, project_comments.c.comment_id == comment_id, Comment)

    def list_comments(self, project_id: str) -> list[Comment]:
        statement = (
            select(project_comments).where(project_comments.c.project_id == project_id).order_by(project_comments.c.created_at)
        )
        return self._all(statement, Comment)

    def delete_comment(self, comment_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(project_comments).where(project_comments.c.comment_id == comment_id))

    # ---- Matriz de literatura ----

    def get_matrix(self, project_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(project_matrices.c.data).where(project_matrices.c.project_id == project_id)).first()
        return row.data if row else None

    def save_matrix(self, project_id: str, data: dict[str, Any], updated_at: str) -> None:
        with self.engine.begin() as conn:
            _upsert(conn, project_matrices, {"project_id": project_id}, {"data": data, "updated_at": updated_at})

    # ---- Pesquisas guardadas ----

    def save_search(self, search: SavedSearch) -> None:
        values = search.model_dump(mode="json")
        with self.engine.begin() as conn:
            _upsert(conn, saved_searches, {"search_id": values.pop("search_id")}, values)

    def get_search(self, search_id: str) -> SavedSearch | None:
        return self._one(saved_searches, saved_searches.c.search_id == search_id, SavedSearch)

    def list_searches(self, owner_id: str) -> list[SavedSearch]:
        statement = select(saved_searches).where(saved_searches.c.owner_id == owner_id).order_by(saved_searches.c.name)
        return self._all(statement, SavedSearch)

    def delete_search(self, search_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(saved_searches).where(saved_searches.c.search_id == search_id))


class SqlFeedbackRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(self, feedback: AnswerFeedback) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(answer_feedback).values(**feedback.model_dump(mode="json")))

    def list_recent(self, limit: int = 200, rating: int | None = None) -> list[AnswerFeedback]:
        statement = select(answer_feedback).order_by(answer_feedback.c.created_at.desc()).limit(limit)
        if rating is not None:
            statement = statement.where(answer_feedback.c.rating == rating)
        with self.engine.connect() as conn:
            return [AnswerFeedback(**row._mapping) for row in conn.execute(statement)]

    def counts(self) -> dict[int, int]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(answer_feedback.c.rating, func.count()).group_by(answer_feedback.c.rating)).all()
        return {rating: count for rating, count in rows}
