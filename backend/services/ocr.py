import re
import threading
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract
from PIL import Image

# O pdfium não é thread-safe (renderizações concorrentes dão segfault); só o tesseract corre em paralelo.
_pdfium_lock = threading.Lock()


@dataclass
class OcrResult:
    text: str
    confidence: float
    word_count: int


def render_page(pdf_path: Path, page_number: int, dpi: int) -> Image.Image:
    with _pdfium_lock:
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            page = pdf[page_number - 1]
            bitmap = page.render(scale=dpi / 72)
            return bitmap.to_pil().convert("L")
        finally:
            pdf.close()


def ocr_image(image: Image.Image, languages: str) -> OcrResult:
    data = pytesseract.image_to_data(image, lang=languages, output_type=pytesseract.Output.DICT)

    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        confidence = float(data["conf"][i])
        # conf == -1 marca blocos sem texto (layout), não palavras.
        if not word or confidence < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confidences.append(confidence)

    raw_text = "\n".join(" ".join(words) for words in lines.values())
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(
        text=clean_ocr_text(raw_text),
        confidence=round(mean_confidence, 1),
        word_count=len(confidences),
    )


def _is_noise_line(line: str) -> bool:
    alnum = sum(ch.isalnum() for ch in line)
    if alnum < 2:
        return True
    # Linhas dominadas por símbolos são tipicamente artefactos (bordas, carimbos, sujidade).
    return alnum / len(line.replace(" ", "")) < 0.5


def clean_ocr_text(text: str) -> str:
    # Junta palavras hifenizadas na quebra de linha: "contra-\nto" -> "contrato".
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    kept = [line for line in lines if line and not _is_noise_line(line)]
    return "\n".join(kept)
