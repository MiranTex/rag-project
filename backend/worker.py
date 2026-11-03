"""Workers da fila num processo à parte: `python -m backend.worker`.

Útil para separar o OCR e os embeddings da API (por exemplo noutro contentor, com INDEXING_WORKERS=0 na API).
Precisa da mesma DATABASE_URL, do mesmo UPLOAD_DIR e do mesmo Chroma que a API.
"""

import logging
import signal
import threading

from backend.api.documents import build_job_runner
from backend.config import get_settings
from backend.dependencies import get_job_queue, install_settings_overrides
from backend.services.job_startup import recover_interrupted_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    install_settings_overrides()
    settings = get_settings()
    recover_interrupted_jobs(get_job_queue(), settings.job_stale_minutes)
    runner = build_job_runner()
    runner.start(max(settings.indexing_workers, 1))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    runner.stop()


if __name__ == "__main__":
    main()
