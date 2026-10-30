import logging
from datetime import UTC, datetime, timedelta

from backend.repositories.contracts import JobQueue
from backend.services.job_runner import worker_prefix

logger = logging.getLogger(__name__)


def recover_interrupted_jobs(queue: JobQueue, stale_minutes: int) -> int:
    """Trabalhos "running" deste contentor (processo anterior morreu) ou parados há demasiado tempo voltam à fila."""
    started_before = (datetime.now(UTC) - timedelta(minutes=stale_minutes)).isoformat()
    requeued = queue.requeue_running(started_before=started_before, worker_prefix=worker_prefix())
    if requeued:
        logger.warning("%d trabalho(s) interrompido(s) voltaram à fila", requeued)
    return requeued
