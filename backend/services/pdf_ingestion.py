import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader


@dataclass
class ChunkRecord:
    id: str
    text: str
    page: int
    chunk_index: int
    document_chunk_count: int = 0


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_uploaded_file(upload_dir: str, filename: str, content: bytes) -> Path:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    target = Path(upload_dir) / safe_name
    target.write_bytes(content)
    return target


def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            normalized = " ".join(text.split())
            pages.append((i, normalized))
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
