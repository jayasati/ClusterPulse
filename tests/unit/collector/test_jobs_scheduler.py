"""Unit tests for PeriodicJobScheduler.

Real threads with tiny intervals, synchronized via events — no sleeps as
assertions, only bounded waits.
"""

import threading

import pytest

from collector.jobs.scheduler import PeriodicJobScheduler

WAIT = 5.0  # generous bound; tests pass in milliseconds when healthy


class RecordingJob:
    def __init__(self, name: str = "recording") -> None:
        self.name = name
        self.run_count = 0
        self.ran = threading.Event()

    def run(self) -> str:
        self.run_count += 1
        self.ran.set()
        return "ok"


class ExplodingJob:
    name = "exploding"

    def __init__(self) -> None:
        self.ran = threading.Event()

    def run(self) -> None:
        self.ran.set()
        raise RuntimeError("job blew up")


def test_rejects_nonpositive_interval() -> None:
    with pytest.raises(ValueError):
        PeriodicJobScheduler(interval_seconds=0, jobs=[])


def test_runs_jobs_periodically_until_stopped() -> None:
    job = RecordingJob()
    scheduler = PeriodicJobScheduler(interval_seconds=0.01, jobs=[job])

    scheduler.start()
    try:
        assert job.ran.wait(WAIT), "job never ran"
    finally:
        scheduler.stop()

    assert job.run_count >= 1
    assert scheduler.is_running is False


def test_job_exception_does_not_kill_the_loop_or_starve_other_jobs() -> None:
    exploding, healthy = ExplodingJob(), RecordingJob()
    scheduler = PeriodicJobScheduler(interval_seconds=0.01, jobs=[exploding, healthy])

    scheduler.start()
    try:
        assert exploding.ran.wait(WAIT)
        assert healthy.ran.wait(WAIT), "job after a failing one never ran"
        # The loop survives the failure: the healthy job keeps accumulating runs.
        healthy.ran.clear()
        assert healthy.ran.wait(WAIT), "loop died after job failure"
    finally:
        scheduler.stop()


def test_stop_before_first_interval_never_runs_jobs() -> None:
    job = RecordingJob()
    scheduler = PeriodicJobScheduler(interval_seconds=3600, jobs=[job])

    scheduler.start()
    scheduler.stop()

    assert job.run_count == 0
    assert scheduler.is_running is False


def test_stop_without_start_is_safe() -> None:
    PeriodicJobScheduler(interval_seconds=1, jobs=[]).stop()


def test_start_is_idempotent_while_running() -> None:
    job = RecordingJob()
    scheduler = PeriodicJobScheduler(interval_seconds=3600, jobs=[job])

    scheduler.start()
    first_thread_alive = scheduler.is_running
    scheduler.start()  # must not spawn a second thread or raise
    try:
        assert first_thread_alive
        assert scheduler.is_running
    finally:
        scheduler.stop()


def test_run_pending_once_runs_every_job_synchronously() -> None:
    jobs = [RecordingJob("a"), RecordingJob("b")]
    scheduler = PeriodicJobScheduler(interval_seconds=3600, jobs=jobs)

    scheduler.run_pending_once()

    assert [job.run_count for job in jobs] == [1, 1]


def test_run_pending_once_contains_exceptions() -> None:
    exploding, healthy = ExplodingJob(), RecordingJob()
    scheduler = PeriodicJobScheduler(interval_seconds=3600, jobs=[exploding, healthy])

    scheduler.run_pending_once()  # must not raise

    assert healthy.run_count == 1
