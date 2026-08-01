import json
from pathlib import Path
from threading import Lock

from backend.models import DocumentInfo


class DocumentRegistry:
    def __init__(self, path: str = "backend/storage/documents.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")
        self._lock = Lock()

    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, docs: list[dict]) -> None:
        self.path.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_documents(self) -> list[DocumentInfo]:
        return [DocumentInfo(**doc) for doc in self._read()]

    def find_by_hash(self, sha256: str) -> DocumentInfo | None:
        for doc in self._read():
            if doc["sha256"] == sha256:
                return DocumentInfo(**doc)
        return None

    def add_or_replace(self, info: DocumentInfo) -> None:
        with self._lock:
            docs = self._read()
            docs = [doc for doc in docs if doc["document_id"] != info.document_id]
            docs.append(info.model_dump())
            self._write(docs)

    def find_by_id(self, document_id: str) -> DocumentInfo | None:
        for doc in self._read():
            if doc["document_id"] == document_id:
                return DocumentInfo(**doc)
        return None

    def remove(self, document_id: str) -> bool:
        with self._lock:
            docs = self._read()
            filtered = [doc for doc in docs if doc["document_id"] != document_id]
            if len(filtered) == len(docs):
                return False
            self._write(filtered)
            return True
