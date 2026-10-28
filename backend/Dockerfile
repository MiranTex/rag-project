FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    # O OCR já corre páginas em paralelo; sem este limite cada tesseract abre threads
    # OpenMP próprias e o CPU fica sobrecarregado (~8x mais lento).
    OMP_THREAD_LIMIT=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

# torch CPU-only evita descarregar as libs CUDA (~GBs) puxadas pelo sentence-transformers
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY tests ./tests
COPY pytest.ini .

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
