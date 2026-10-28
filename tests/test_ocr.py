import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.services.ocr import clean_ocr_text
from backend.services.pdf_ingestion import extract_pages


def test_clean_ocr_text_joins_hyphenated_line_breaks():
    assert clean_ocr_text("o contra-\nto de trabalho") == "o contrato de trabalho"


def test_clean_ocr_text_drops_symbol_noise_lines():
    raw = "Cláusula 1.ª\n| ~ — . |\n,,\nO trabalhador obriga-se a cumprir"
    assert clean_ocr_text(raw) == "Cláusula 1.ª\nO trabalhador obriga-se a cumprir"


def test_clean_ocr_text_collapses_spaces():
    assert clean_ocr_text("  Data   de  início:\t 01/02/2024 ") == "Data de início: 01/02/2024"


def _image_only_pdf(path, lines: list[str]) -> None:
    image = Image.new("L", (1700, 2200), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    for i, line in enumerate(lines):
        draw.text((120, 150 + i * 90), line, fill=0, font=font)
    image.save(path, "PDF", resolution=200)


def test_extract_pages_without_ocr_skips_image_pages(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _image_only_pdf(pdf_path, ["Contrato de trabalho"])

    assert extract_pages(pdf_path) == []


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract não instalado")
def test_extract_pages_applies_ocr_to_image_pages(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _image_only_pdf(pdf_path, ["Contrato de trabalho", "Retribuição mensal de 1500 euros"])

    pages = extract_pages(pdf_path, ocr_languages="por+eng")

    assert len(pages) == 1
    page = pages[0]
    assert page.source == "ocr"
    assert page.ocr_confidence is not None and page.ocr_confidence > 60
    assert "Contrato de trabalho" in page.text
    assert "1500 euros" in page.text
