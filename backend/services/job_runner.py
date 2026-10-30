import logging
import os
import socket
import threading
from collections.abc import Callable

from backend.models import Job
from backend.repositories.contracts import JobQueue

logger = logging.getLogger(__name__)

JobHandler = Callable[[Job], None]
FailureHandler = Callable[[Job, str], None]


def worker_prefix() -> str:
    """Identifica esta máquina/contentor: ao arrancar, os trabalhos que ficaram "running" com este prefixo
    são de um processo anterior que morreu e voltam à fila."""
    return f"{socket.gethostname()}:"


def error_message(exc: Exception) -> str:
    # HTTPException guarda a mensagem em detail; as outras exceções no texto.
    return str(getattr(exc, "detail", "") or exc) or type(exc).__name__


class JobRunner:
    """Consome a fila de trabalhos com um handler por tipo ("extract", "index"...). Pode correr dentro da API
    (start, em threads) ou num processo à parte (backend/worker.py); nos testes, run_until_idle."""

    def __init__(
        self,
        queue: JobQueue,
        handlers: dict[str, JobHandler],
        on_failure: FailureHandler | None = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self.queue = queue
        self.handlers = handlers
        self.on_failure = on_failure
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def run_once(self, worker_id: str) -> bool:
        """Processa um trabalho; devolve False se a fila estava vazia."""
        job = self.queue.claim_next(worker_id)
        if job is None:
            return False
        handler = self.handlers.get(job.kind)
        try:
            if handler is None:
                raise ValueError(f"Tipo de trabalho desconhecido: {job.kind}")
            logger.info("Trabalho %d (%s) de %s: a começar", job.id, job.kind, job.document_id)
            handler(job)
        except Exception as exc:
            message = error_message(exc)
            logger.exception("Trabalho %d (%s) de %s falhou: %s", job.id, job.kind, job.document_id, message)
            self.queue.fail(job.id, message)
            if self.on_failure:
                try:
                    self.on_failure(job, message)
                except Exception:
                    logger.exception("Falha a registar o erro do trabalho %d", job.id)
        else:
            self.queue.complete(job.id)
            logger.info("Trabalho %d (%s) de %s: concluído", job.id, job.kind, job.document_id)
        return True

    def run_until_idle(self, worker_id: str = "inline", max_jobs: int = 1000) -> int:
        processed = 0
        while processed < max_jobs and self.run_once(worker_id):
            processed += 1
        return processed

    def start(self, threads: int) -> None:
        prefix = f"{worker_prefix()}{os.getpid()}"
        for number in range(threads):
            worker_id = f"{prefix}:{number}"
            thread = threading.Thread(target=self._loop, args=(worker_id,), name=f"job-worker-{number}", daemon=True)
            thread.start()
            self._threads.append(thread)
        logger.info("Fila de trabalhos: %d worker(s) a correr", threads)

    def _loop(self, worker_id: str) -> None:
        while not self._stop.is_set():
            try:
                if not self.run_once(worker_id):
                    self._stop.wait(self.poll_seconds)
            except Exception:
                # Erro da própria fila (ex.: base de dados em baixo): espera e tenta de novo.
                logger.exception("Erro no worker %s", worker_id)
                self._stop.wait(self.poll_seconds * 5)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout)
        self._threads.clear()
