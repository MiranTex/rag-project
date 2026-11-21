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

# Modelo de embeddings descarregado na construção da imagem (fica em HF_HOME): o arranque não depende da
# rede nem demora a descarregar. Tem de ser o mesmo EMBEDDING_MODEL que a aplicação usa.
# (ARG e não ENV: em execução continua a valer o EMBEDDING_MODEL do .env ou do ambiente.)
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "import sys; from sentence_transformers import SentenceTransformer; SentenceTransformer(sys.argv[1])" "$EMBEDDING_MODEL"

COPY backend ./backend
COPY tests ./tests
COPY pytest.ini .

# Com PostgreSQL (DATABASE_URL) e storage S3 (STORAGE_*) nada fica no disco do contentor: backend/storage e
# data/ só se usam com SQLite e ficheiros locais (docker-compose, com volumes).
EXPOSE 8000

# PORT é injetada pelas plataformas (ex.: Base Stack); 8000 por defeito.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
