"""Implementação SQL dos contratos com SQLAlchemy Core: a mesma para SQLite e PostgreSQL (só muda a
DATABASE_URL). O esquema evolui com as migrações Alembic em repositories/migrations."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    func,
    insert,
    or_,
    select,
    update,
)

from backend.models import DocumentInfo, DocumentMetadata, Job, ReviewPage, User

metadata_obj = MetaData()

documents = Table(
    "documents",
    metadata_obj,
    Column("document_id", String(64), primary_key=True),
    Column("filename", String(255), nullable=False),
    Column("original_filename", String(255), nullable=False, default=""),
    Column("storage_name", String(255), nullable=False, default=""),
    Column("name_source", String(16), nullable=False, default="original"),
    Column("sha256", String(64), nullable=False, index=True),
    Column("created_at", String(40), nullable=False),
    Column("chunk_count", Integer, nullable=False, default=0),
    Column("status", String(32), nullable=False),
    Column("page_count", Integer, nullable=False, default=0),
    Column("alert_count", Integer, nullable=False, default=0),
    Column("title", Text, nullable=False, default=""),
    Column("year", Integer, nullable=True),
    Column("document_type", String(64), nullable=False, default=""),
    Column("error", Text, nullable=False, default=""),
    Column("uploaded_by", String(64), nullable=False, default=""),
    Column("approved_by", String(64), nullable=False, default=""),
    Column("approved_fingerprint", String(64), nullable=False, default=""),
)

users = Table(
    "users",
    metadata_obj,
    Column("user_id", String(64), primary_key=True),
    Column("username", String(255), nullable=False, unique=True),
    Column("display_name", String(255), nullable=False, default=""),
    Column("roles", JSON, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("external_id", String(255), nullable=True, unique=True),
    Column("password_hash", String(255), nullable=False, default=""),
    Column("created_at", String(40), nullable=False),
)

extraction_pages = Table(
    "extraction_pages",
    metadata_obj,
    Column("document_id", String(64), primary_key=True),
    Column("page", Integer, primary_key=True),
    Column("text", Text, nullable=False),
    Column("source", String(16), nullable=False),
    Column("ocr_confidence", Float, nullable=True),
    Column("alerts", JSON, nullable=False),
    Column("excluded", Boolean, nullable=False, default=False),
    Column("edited", Boolean, nullable=False, default=False),
)

document_metadata = Table(
    "document_metadata",
    metadata_obj,
    Column("document_id", String(64), primary_key=True),
    Column("data", JSON, nullable=False),
)

jobs = Table(
    "jobs",
    metadata_obj,
    # Inteiro sequencial: a ordem dos ids é a ordem da fila em qualquer base de dados.
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", String(32), nullable=False),
    Column("document_id", String(64), nullable=False, index=True),
    Column("status", String(16), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("error", Text, nullable=False, default=""),
    Column("attempts", Integer, nullable=False, default=0),
    Column("worker_id", String(128), nullable=False, default=""),
    Column("created_at", String(40), nullable=False),
    Column("started_at", String(40), nullable=True),
    Column("finished_at", String(40), nullable=True),
)

ACTIVE_JOB_STATUSES = ("queued", "running")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_db_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # Workers em threads: a ligação passa entre threads; WAL deixa ler enquanto um worker escreve.
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


class SqlDocumentRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _to_model(row) -> DocumentInfo:
        return DocumentInfo(**row._mapping)

    def list_documents(self) -> list[DocumentInfo]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(documents).order_by(documents.c.created_at, documents.c.document_id))
            return [self._to_model(row) for row in rows]

    def find_by_id(self, document_id: str) -> DocumentInfo | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(documents).where(documents.c.document_id == document_id)).first()
        return self._to_model(row) if row else None

    def find_by_hash(self, sha256: str) -> DocumentInfo | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(documents).where(documents.c.sha256 == sha256).limit(1)).first()
        return self._to_model(row) if row else None

    def add_or_replace(self, info: DocumentInfo) -> None:
        values = info.model_dump()
        with self.engine.begin() as conn:
            result = conn.execute(update(documents).where(documents.c.document_id == info.document_id).values(**values))
            if result.rowcount == 0:
                conn.execute(insert(documents).values(**values))

    def remove(self, document_id: str) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(delete(documents).where(documents.c.document_id == document_id)).rowcount > 0


class SqlUserRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _to_model(row) -> User:
        return User(**{k: v for k, v in row._mapping.items() if k != "password_hash"})

    def _find(self, condition) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(condition)).first()
        return self._to_model(row) if row else None

    def list_users(self) -> list[User]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(users).order_by(users.c.username))
            return [self._to_model(row) for row in rows]

    def find_by_id(self, user_id: str) -> User | None:
        return self._find(users.c.user_id == user_id)

    def find_by_username(self, username: str) -> User | None:
        return self._find(users.c.username == username)

    def find_by_external_id(self, external_id: str) -> User | None:
        return self._find(users.c.external_id == external_id)

    def add_or_replace(self, user: User) -> None:
        values = user.model_dump()
        with self.engine.begin() as conn:
            result = conn.execute(update(users).where(users.c.user_id == user.user_id).values(**values))
            if result.rowcount == 0:
                conn.execute(insert(users).values(**values, password_hash=""))

    def password_hash(self, user_id: str) -> str:
        with self.engine.connect() as conn:
            row = conn.execute(select(users.c.password_hash).where(users.c.user_id == user_id)).first()
        return row.password_hash if row else ""

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.user_id == user_id).values(password_hash=password_hash))

    def count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(users)).scalar_one()


class SqlExtractionRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save(self, document_id: str, pages: list[ReviewPage]) -> None:
        rows = [{"document_id": document_id, **page.model_dump(mode="json")} for page in pages]
        with self.engine.begin() as conn:
            conn.execute(delete(extraction_pages).where(extraction_pages.c.document_id == document_id))
            if rows:
                conn.execute(insert(extraction_pages), rows)

    def load(self, document_id: str) -> list[ReviewPage] | None:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(extraction_pages).where(extraction_pages.c.document_id == document_id).order_by(extraction_pages.c.page)
            ).all()
        if not rows:
            return None
        return [ReviewPage(**{k: v for k, v in row._mapping.items() if k != "document_id"}) for row in rows]

    def save_metadata(self, document_id: str, metadata: DocumentMetadata) -> None:
        data = metadata.model_dump(mode="json")
        with self.engine.begin() as conn:
            result = conn.execute(
                update(document_metadata).where(document_metadata.c.document_id == document_id).values(data=data)
            )
            if result.rowcount == 0:
                conn.execute(insert(document_metadata).values(document_id=document_id, data=data))

    def load_metadata(self, document_id: str) -> DocumentMetadata:
        with self.engine.connect() as conn:
            row = conn.execute(select(document_metadata.c.data).where(document_metadata.c.document_id == document_id)).first()
        return DocumentMetadata(**row.data) if row else DocumentMetadata()

    def delete(self, document_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(extraction_pages).where(extraction_pages.c.document_id == document_id))
            conn.execute(delete(document_metadata).where(document_metadata.c.document_id == document_id))


class SqlJobQueue:
    CLAIM_ATTEMPTS = 5

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _to_model(row) -> Job:
        return Job(**row._mapping)

    def enqueue(self, kind: str, document_id: str, payload: dict | None = None) -> Job:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(jobs).values(
                    kind=kind,
                    document_id=document_id,
                    status="queued",
                    payload=payload or {},
                    error="",
                    attempts=0,
                    worker_id="",
                    created_at=_now(),
                )
            )
            job_id = result.inserted_primary_key[0]
        return self.get(job_id)

    def claim_next(self, worker_id: str) -> Job | None:
        # Sem locks específicos da base de dados: escolhe o mais antigo e só o fica se o UPDATE condicional
        # ainda o encontrar em fila; se outro worker o levou entretanto, tenta o seguinte.
        for _ in range(self.CLAIM_ATTEMPTS):
            with self.engine.begin() as conn:
                row = conn.execute(select(jobs.c.id).where(jobs.c.status == "queued").order_by(jobs.c.id).limit(1)).first()
                if row is None:
                    return None
                claimed = conn.execute(
                    update(jobs)
                    .where(jobs.c.id == row.id, jobs.c.status == "queued")
                    .values(status="running", worker_id=worker_id, started_at=_now(), attempts=jobs.c.attempts + 1)
                ).rowcount
            if claimed == 1:
                return self.get(row.id)
        return None

    def _finish(self, job_id: int, status: str, error: str = "") -> None:
        with self.engine.begin() as conn:
            conn.execute(update(jobs).where(jobs.c.id == job_id).values(status=status, error=error, finished_at=_now()))

    def complete(self, job_id: int) -> None:
        self._finish(job_id, "done")

    def fail(self, job_id: int, error: str) -> None:
        self._finish(job_id, "failed", error)

    def get(self, job_id: int) -> Job | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(jobs).where(jobs.c.id == job_id)).first()
        return self._to_model(row) if row else None

    def active_for_document(self, document_id: str) -> Job | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(jobs)
                .where(jobs.c.document_id == document_id, jobs.c.status.in_(ACTIVE_JOB_STATUSES))
                .order_by(jobs.c.id)
                .limit(1)
            ).first()
        return self._to_model(row) if row else None

    def cancel_queued(self, document_id: str) -> int:
        with self.engine.begin() as conn:
            return conn.execute(delete(jobs).where(jobs.c.document_id == document_id, jobs.c.status == "queued")).rowcount

    def requeue_running(self, started_before: str | None = None, worker_prefix: str | None = None) -> int:
        conditions = []
        if started_before:
            conditions.append(jobs.c.started_at < started_before)
        if worker_prefix:
            conditions.append(jobs.c.worker_id.startswith(worker_prefix))
        if not conditions:
            return 0
        with self.engine.begin() as conn:
            return conn.execute(
                update(jobs)
                .where(jobs.c.status == "running", or_(*conditions))
                .values(status="queued", worker_id="", started_at=None)
            ).rowcount

    def counts(self) -> dict[str, int]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(jobs.c.status, func.count()).group_by(jobs.c.status)).all()
        return {status: count for status, count in rows}
