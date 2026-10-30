"""Contrato de JobQueue e comportamento do JobRunner."""

import threading

import pytest

from backend.repositories.sql import SqlJobQueue
from backend.services.job_runner import JobRunner
from tests.repository_fixtures import SQL_BACKENDS, sql_engine


@pytest.fixture(params=SQL_BACKENDS)
def queue(request, tmp_path):
    return SqlJobQueue(sql_engine(request.param, tmp_path))


def test_jobs_are_claimed_in_order(queue):
    first = queue.enqueue("extract", "d1", {"new": True})
    queue.enqueue("index", "d2")

    assert (first.status, first.payload, first.attempts) == ("queued", {"new": True}, 0)
    claimed = queue.claim_next("w1")
    assert (claimed.id, claimed.status, claimed.worker_id, claimed.attempts) == (first.id, "running", "w1", 1)
    assert claimed.started_at
    assert queue.claim_next("w1").document_id == "d2"
    assert queue.claim_next("w1") is None


def test_complete_fail_and_counts(queue):
    a = queue.enqueue("extract", "d1")
    b = queue.enqueue("extract", "d2")
    queue.enqueue("extract", "d3")
    queue.claim_next("w")
    queue.claim_next("w")
    queue.complete(a.id)
    queue.fail(b.id, "PDF corrompido")

    assert queue.get(a.id).status == "done" and queue.get(a.id).finished_at
    assert (queue.get(b.id).status, queue.get(b.id).error) == ("failed", "PDF corrompido")
    assert queue.counts() == {"done": 1, "failed": 1, "queued": 1}
    assert queue.get(9999) is None


def test_active_job_and_cancel(queue):
    queue.enqueue("extract", "d1")
    assert queue.active_for_document("d1").kind == "extract"
    assert queue.active_for_document("d2") is None

    queue.claim_next("w")
    queue.enqueue("index", "d1")
    # Só os que ainda estão em fila se cancelam; o que corre continua ativo.
    assert queue.cancel_queued("d1") == 1
    assert queue.active_for_document("d1").status == "running"


def test_requeue_running_by_worker_prefix_or_age(queue):
    queue.enqueue("extract", "d1")
    queue.enqueue("extract", "d2")
    queue.claim_next("host-a:1:0")
    queue.claim_next("host-b:7:0")

    assert queue.requeue_running() == 0
    assert queue.requeue_running(worker_prefix="host-a:") == 1
    assert queue.claim_next("host-c:1:0").document_id == "d1"
    # Tudo o que começou antes de um instante no futuro está parado.
    assert queue.requeue_running(started_before="2999-01-01T00:00:00+00:00") == 2


def test_concurrent_workers_never_take_the_same_job(queue):
    total = 30
    for i in range(total):
        queue.enqueue("extract", f"d{i}")
    taken: list[int] = []
    lock = threading.Lock()

    def worker(name):
        while (job := queue.claim_next(name)) is not None:
            with lock:
                taken.append(job.id)

    threads = [threading.Thread(target=worker, args=(f"w{n}",)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(taken) == total and len(set(taken)) == total


def test_runner_completes_fails_and_reports(queue):
    failures = []
    handled = []

    def ok(job):
        handled.append(job.document_id)

    def broken(job):
        raise RuntimeError("Chroma em baixo")

    runner = JobRunner(queue, {"extract": ok, "index": broken}, on_failure=lambda job, msg: failures.append((job.kind, msg)))
    good = queue.enqueue("extract", "d1")
    bad = queue.enqueue("index", "d2")
    unknown = queue.enqueue("translate", "d3")

    assert runner.run_until_idle() == 3
    assert handled == ["d1"]
    assert queue.get(good.id).status == "done"
    assert (queue.get(bad.id).status, queue.get(bad.id).error) == ("failed", "Chroma em baixo")
    assert queue.get(unknown.id).status == "failed"
    assert failures == [("index", "Chroma em baixo"), ("translate", "Tipo de trabalho desconhecido: translate")]


def test_runner_threads_process_the_queue(queue):
    done = threading.Event()
    seen = []

    def handler(job):
        seen.append(job.document_id)
        if len(seen) == 3:
            done.set()

    runner = JobRunner(queue, {"extract": handler}, poll_seconds=0.05)
    runner.start(2)
    for i in range(3):
        queue.enqueue("extract", f"d{i}")
    assert done.wait(5)
    runner.stop()
    assert sorted(seen) == ["d0", "d1", "d2"]
