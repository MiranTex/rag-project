import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from backend.services.ocr import ocr_image, render_page

logger = logging.getLogger(__name__)


@dataclass
class ChunkRecord:
    id: str
    text: str
    page: int
    chunk_index: int
    document_chunk_count: int = 0


@dataclass
class ExtractedPage:
    page: int
    text: str
    source: str  # "text" (camada de texto do PDF) ou "ocr"
    ocr_confidence: float | None = None


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_uploaded_file(upload_dir: str, filename: str, content: bytes) -> Path:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    target = Path(upload_dir) / safe_name
    target.write_bytes(content)
    return target


def extract_pages(
    pdf_path: Path,
    ocr_languages: str | None = None,
    ocr_dpi: int = 300,
    ocr_min_text_chars: int = 30,
    ocr_min_confidence: float = 60.0,
    ocr_max_workers: int = 4,
) -> list[ExtractedPage]:
    """Extrai o texto de cada página; páginas sem camada de texto passam por OCR se ocr_languages estiver definido."""
    reader = PdfReader(str(pdf_path))
    pages: list[ExtractedPage] = []
    ocr_candidates: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        text = " ".join((page.extract_text() or "").split())
        if len(text) >= ocr_min_text_chars:
            pages.append(ExtractedPage(page=i, text=text, source="text"))
        else:
            ocr_candidates.append(i)

    if ocr_candidates and not ocr_languages:
        logger.warning("%s: %d página(s) sem texto ignoradas (OCR desativado): %s", pdf_path.name, len(ocr_candidates), ocr_candidates)
    elif ocr_candidates:
        logger.info("%s: a aplicar OCR a %d página(s): %s", pdf_path.name, len(ocr_candidates), ocr_candidates)

        def run_ocr(page_number: int):
            return page_number, ocr_image(render_page(pdf_path, page_number, ocr_dpi), ocr_languages)

        with ThreadPoolExecutor(max_workers=max(1, ocr_max_workers)) as pool:
            for page_number, result in pool.map(run_ocr, ocr_candidates):
                if not result.text:
                    logger.warning("%s p.%d: OCR não encontrou texto", pdf_path.name, page_number)
                    continue
                log = logger.warning if result.confidence < ocr_min_confidence else logger.info
                log(
                    "%s p.%d: OCR %d palavras, confiança média %.1f%s",
                    pdf_path.name,
                    page_number,
                    result.word_count,
                    result.confidence,
                    " (baixa — rever texto)" if result.confidence < ocr_min_confidence else "",
                )
                pages.append(
                    ExtractedPage(
                        page=page_number,
                        text=" ".join(result.text.split()),
                        source="ocr",
                        ocr_confidence=result.confidence,
                    )
                )

    pages.sort(key=lambda p: p.page)
    return pages


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    return parts if parts else [normalized]


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    words = sentence.split()
    if len(sentence) <= max_chars:
        return [sentence]

    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(word), max_chars):
                chunks.append(word[start : start + max_chars])
            continue

        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current.strip())
    return chunks


def _finalize_chunk(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped[-1] not in ".!?":
        return f"{stripped}."
    return stripped


def chunk_pages(
    pages: list[tuple[int, str]],
    document_id: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    global_chunk_index = 0

    for page, page_text in pages:
        normalized_text = re.sub(r"\s+", " ", page_text).strip()
        if not normalized_text:
            continue

        fragments: list[str] = []
        for sentence in _split_sentences(normalized_text):
            sentence_text = sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
            if len(sentence_text) > chunk_size:
                fragments.extend(_split_long_sentence(sentence_text, chunk_size))
            else:
                fragments.append(sentence_text)

        buffer = ""
        overlap_tail = ""
        for fragment in fragments:
            candidate = f"{buffer} {fragment}".strip() if buffer else fragment
            if buffer and len(candidate) > chunk_size:
                chunk_text = _finalize_chunk(buffer)
                chunk_id = f"{document_id}:{global_chunk_index}"
                chunks.append(
                    ChunkRecord(
                        id=chunk_id,
                        text=chunk_text,
                        page=page,
                        chunk_index=global_chunk_index,
                    )
                )
                global_chunk_index += 1
                overlap_tail = buffer[-max(chunk_overlap, 0) :] if chunk_overlap else ""
                buffer = fragment
                if overlap_tail:
                    buffer = f"{overlap_tail} {buffer}".strip()
            else:
                buffer = candidate

        if buffer.strip():
            chunk_text = _finalize_chunk(buffer)
            chunk_id = f"{document_id}:{global_chunk_index}"
            chunks.append(
                ChunkRecord(
                    id=chunk_id,
                    text=chunk_text,
                    page=page,
                    chunk_index=global_chunk_index,
                )
            )
            global_chunk_index += 1

    total_chunks = len(chunks)
    for chunk in chunks:
        chunk.document_chunk_count = total_chunks

    return chunks


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
