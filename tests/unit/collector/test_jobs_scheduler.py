"""Unit tests for PeriodicJobScheduler.

Real threads with tiny intervals, synchronized via events — no sleeps as
assertions, only bounded waits.
"""

import threading

import pytest

from collector.jobs.scheduler import JobSchedule, PeriodicJobScheduler

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
        JobSchedule(RecordingJob(), interval_seconds=0)


def test_runs_jobs_periodically_until_stopped() -> None:
    job = RecordingJob()
    scheduler = PeriodicJobScheduler([JobSchedule(job, interval_seconds=0.01)])

    scheduler.start()
    try:
        assert job.ran.wait(WAIT), "job never ran"
    finally:
        scheduler.stop()

    assert job.run_count >= 1
    assert scheduler.is_running is False


def test_each_job_runs_on_its_own_interval() -> None:
    """A fast job must keep running while a slow job's first tick is still
    hours away — the per-job-interval contract."""
    fast, slow = RecordingJob("fast"), RecordingJob("slow")
    scheduler = PeriodicJobScheduler(
        [JobSchedule(fast, interval_seconds=0.01), JobSchedule(slow, 3600)]
    )

    scheduler.start()
    try:
        assert fast.ran.wait(WAIT)
        fast.ran.clear()
        assert fast.ran.wait(WAIT), "fast job did not keep running"
    finally:
        scheduler.stop()

    assert fast.run_count >= 2
    assert slow.run_count == 0


def test_job_exception_does_not_kill_the_loop_or_starve_other_jobs() -> None:
    exploding, healthy = ExplodingJob(), RecordingJob()
    scheduler = PeriodicJobScheduler(
        [JobSchedule(exploding, 0.01), JobSchedule(healthy, 0.01)]
    )

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
    scheduler = PeriodicJobScheduler([JobSchedule(job, 3600)])

    scheduler.start()
    scheduler.stop()

    assert job.run_count == 0
    assert scheduler.is_running is False


def test_stop_without_start_is_safe() -> None:
    PeriodicJobScheduler([]).stop()


def test_scheduler_with_no_jobs_exits_cleanly() -> None:
    scheduler = PeriodicJobScheduler([])
    scheduler.start()
    scheduler.stop()
    assert scheduler.is_running is False


def test_start_is_idempotent_while_running() -> None:
    job = RecordingJob()
    scheduler = PeriodicJobScheduler([JobSchedule(job, 3600)])

    scheduler.start()
    first_thread_alive = scheduler.is_running
    scheduler.start()  # must not spawn a second thread or raise
    try:
        assert first_thread_alive
        assert scheduler.is_running
    finally:
        scheduler.stop()


def test_run_all_once_runs_every_job_synchronously() -> None:
    jobs = [RecordingJob("a"), RecordingJob("b")]
    scheduler = PeriodicJobScheduler([JobSchedule(job, 3600) for job in jobs])

    scheduler.run_all_once()

    assert [job.run_count for job in jobs] == [1, 1]


def test_run_all_once_contains_exceptions() -> None:
    exploding, healthy = ExplodingJob(), RecordingJob()
    scheduler = PeriodicJobScheduler(
        [JobSchedule(exploding, 3600), JobSchedule(healthy, 3600)]
    )

    scheduler.run_all_once()  # must not raise

    assert healthy.run_count == 1
