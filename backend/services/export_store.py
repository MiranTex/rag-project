import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ExportedFile:
    name: str
    size: int
    created_at: str


class ExportStore:
    """Guarda os ficheiros gerados pelo agente num diretório próprio, sem nunca sobrescrever."""

    def __init__(self, export_dir: str) -> None:
        self.root = Path(export_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _slugify(name: str) -> str:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_name).strip("-._")
        return slug[:80] or "export"

    def reserve_path(self, filename: str, extension: str) -> Path:
        stem = self._slugify(Path(filename).stem)
        candidate = self.root / f"{stem}.{extension}"
        counter = 2
        while candidate.exists():
            candidate = self.root / f"{stem}-{counter}.{extension}"
            counter += 1
        return candidate

    def resolve(self, name: str) -> Path | None:
        path = (self.root / name).resolve()
        if path.parent != self.root.resolve() or not path.is_file():
            return None
        return path

    def list_files(self) -> list[ExportedFile]:
        files = [p for p in self.root.iterdir() if p.is_file() and not p.name.startswith(".")]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [
            ExportedFile(
                name=p.name,
                size=p.stat().st_size,
                created_at=datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(),
            )
            for p in files
        ]
