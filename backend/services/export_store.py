import mimetypes
import re
import tempfile
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.services.object_storage import LocalStorage, ObjectStorage

_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


@dataclass
class ExportedFile:
    name: str
    size: int
    created_at: str


class ExportStore:
    """Guarda os ficheiros gerados pelo agente (no disco local ou no storage S3), sem nunca sobrescrever."""

    def __init__(self, storage: ObjectStorage | str | Path, prefix: str = "") -> None:
        # Uma pasta (str/Path) continua a funcionar: é o storage local nessa pasta.
        self.storage = LocalStorage(storage) if isinstance(storage, str | Path) else storage
        self.prefix = prefix

    def for_owner(self, owner_id: str) -> "ExportStore":
        """Pasta só de um utilizador: cada um lista e descarrega apenas o que o agente gerou para si."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", owner_id):
            raise ValueError(f"Id de utilizador inválido para exports: {owner_id!r}")
        return ExportStore(self.storage, f"{self.prefix}{owner_id}/")

    @staticmethod
    def _slugify(name: str) -> str:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_name).strip("-._")
        return slug[:80] or "export"

    def _key(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def reserve_name(self, filename: str, extension: str) -> str:
        stem = self._slugify(Path(filename).stem)
        candidate = f"{stem}.{extension}"
        counter = 2
        while self.storage.exists(self._key(candidate)):
            candidate = f"{stem}-{counter}.{extension}"
            counter += 1
        return candidate

    def create(self, filename: str, extension: str, write: Callable[[Path], None]) -> str:
        """Escolhe um nome livre, escreve o ficheiro com write(caminho temporário) e guarda-o; devolve o nome."""
        name = self.reserve_name(filename, extension)
        with tempfile.TemporaryDirectory(prefix="rag-export-") as folder:
            path = Path(folder) / name
            write(path)
            self.storage.put(self._key(name), path.read_bytes())
        return name

    def read(self, name: str) -> bytes | None:
        """Conteúdo de um ficheiro deste utilizador; None se não existir ou se o nome sair da pasta."""
        if not _NAME.fullmatch(name):
            return None
        return self.storage.get(self._key(name))

    @staticmethod
    def media_type(name: str) -> str:
        return mimetypes.guess_type(name)[0] or "application/octet-stream"

    def list_files(self) -> list[ExportedFile]:
        files = sorted(self.storage.list(self.prefix), key=lambda item: item.modified, reverse=True)
        return [
            ExportedFile(name=item.key.rsplit("/", 1)[-1], size=item.size, created_at=item.modified.isoformat())
            for item in files
        ]
