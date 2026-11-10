import json
import re
from pathlib import Path
from threading import Lock

from backend.models import DocumentMetadata, PageAlert, ReviewPage

# Palavra "bem formada": letras/dígitos, opcionalmente ligados por - ' . / , : (ex.: "obriga-se", "01/02/2024", "1.500,00").
_WORD_RE = re.compile(r"^[^\W_]+(?:[-'’./,:][^\W_]+)*$")
_EDGE_PUNCT = "\"'“”‘’«»()[]{}.,;:!?…%€$ºª*"
_VOWELS = set("aeiouyáàâãéèêíìîóòôõúùûü")
# Texto UTF-8 lido como Latin-1: "Ã§" em vez de "ç", "Ã©" em vez de "é".
_MOJIBAKE_RE = re.compile(r"Ã[\u0080-¿]|â€")
# Glifos sem mapeamento Unicode que o pypdf devolve como "(cid:123)".
_CID_RE = re.compile(r"\(cid:\d+\)")


def _is_suspicious_word(token: str) -> bool:
    word = token.strip(_EDGE_PUNCT)
    if not word:
        return False
    if not _WORD_RE.match(word):
        return True
    # Sequências longas de letras sem vogais ("rnnl", "lllh") são típicas de OCR mal lido.
    return word.isalpha() and len(word) >= 4 and not (set(word.lower()) & _VOWELS)


def garbled_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    return sum(_is_suspicious_word(t) for t in tokens) / len(tokens)


def validate_page(
    text: str,
    source: str,
    ocr_confidence: float | None,
    min_text_chars: int,
    min_confidence: float,
    max_garbled_ratio: float,
) -> list[PageAlert]:
    """Verificações automáticas sobre o texto extraído de uma página; cada problema encontrado vira um alerta."""
    if not text.strip():
        return [PageAlert(code="empty", message="Sem texto extraído.")]

    alerts: list[PageAlert] = []
    if len(text) < min_text_chars:
        alerts.append(PageAlert(code="short", message=f"Pouco texto ({len(text)} caracteres)."))
    if source == "ocr" and ocr_confidence is not None and ocr_confidence < min_confidence:
        alerts.append(
            PageAlert(
                code="low_confidence",
                message=f"Confiança do OCR baixa ({ocr_confidence:.1f} < {min_confidence:.0f}).",
            )
        )
    ratio = garbled_ratio(text)
    if ratio > max_garbled_ratio:
        alerts.append(PageAlert(code="garbled", message=f"{ratio:.0%} das palavras parecem mal lidas."))
    if "�" in text or _MOJIBAKE_RE.search(text) or _CID_RE.search(text):
        alerts.append(PageAlert(code="encoding", message="Caracteres com encoding partido."))
    return alerts


class ExtractionStore:
    """Extrações e fichas em ficheiros JSON (versão anterior à base de dados). Cumpre ExtractionRepository;
    hoje serve para importar os dados antigos (ver repositories/legacy_import.py)."""

    def __init__(self, directory: str = "backend/storage/extractions") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path(self, document_id: str) -> Path:
        return self.directory / f"{document_id}.json"

    def save(self, document_id: str, pages: list[ReviewPage]) -> None:
        payload = json.dumps([page.model_dump() for page in pages], indent=2, ensure_ascii=False)
        with self._lock:
            tmp = self._path(document_id).with_suffix(".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self._path(document_id))

    def load(self, document_id: str) -> list[ReviewPage] | None:
        path = self._path(document_id)
        if not path.exists():
            return None
        return [ReviewPage(**page) for page in json.loads(path.read_text(encoding="utf-8"))]

    def _metadata_path(self, document_id: str) -> Path:
        return self.directory / f"{document_id}.metadata.json"

    def save_metadata(self, document_id: str, metadata: DocumentMetadata) -> None:
        with self._lock:
            tmp = self._metadata_path(document_id).with_suffix(".tmp")
            tmp.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(self._metadata_path(document_id))

    def load_metadata(self, document_id: str) -> DocumentMetadata:
        path = self._metadata_path(document_id)
        if not path.exists():
            return DocumentMetadata()
        return DocumentMetadata.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, document_id: str) -> None:
        self._path(document_id).unlink(missing_ok=True)
        self._metadata_path(document_id).unlink(missing_ok=True)
