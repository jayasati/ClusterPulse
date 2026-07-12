"""A minimal thread-based periodic job scheduler with per-job intervals.

One daemon thread runs every registered job on its own cadence: the loop
sleeps until the soonest job is due, runs everything that is due, and
repeats. A thread (not an asyncio task) is deliberate: the Collector's
entire persistence stack is synchronous SQLAlchemy
(``docs/adr/017-collector-sync-vs-async-db.md``), so jobs block on I/O —
exactly what a worker thread is for, and exactly what would stall the
event loop if scheduled there.

Failure containment: a job raising is *contained* — logged with its name,
the remaining due jobs still run, and the loop continues. The thread can
only exit via ``stop()``. Overlapping runs are impossible by
construction: one thread runs all jobs sequentially. The cost of that
simplicity — one slow job delays another's tick — is acceptable at this
scale and documented in ``docs/adr/022-staleness-reconciliation-jobs.md``.
"""

import threading
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

import structlog

logger = structlog.get_logger(__name__)


class Job(Protocol):
    """Anything the scheduler can run periodically."""

    @property
    def name(self) -> str:
        """Stable identifier used in logs."""
        ...

    def run(self) -> object:
        """Execute one run. Return value is logged, not interpreted."""
        ...


@dataclass
class JobSchedule:
    """A job plus how often it should run."""

    job: Job
    interval_seconds: float

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")


class _Entry:
    """Internal mutable pairing of a schedule with its next-due time."""

    def __init__(self, schedule: JobSchedule, now: float) -> None:
        self.schedule = schedule
        self.next_due = now + schedule.interval_seconds


class PeriodicJobScheduler:
    """Runs each scheduled job on its own interval, on one daemon thread.

    Every job's first run happens one full interval after ``start()`` —
    startup is already the Collector's busiest moment (migrations just
    ran, agents reconnect and drain buffers), so deferring the first
    sweep keeps boot predictable.
    """

    def __init__(self, schedules: Sequence[JobSchedule]) -> None:
        self._schedules = list(schedules)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        """Whether the scheduler thread is currently alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the scheduler thread. Idempotent while already running."""
        if self.is_running:
            logger.warning("job_scheduler_already_running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="clusterpulse-job-scheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "job_scheduler_started",
            jobs={
                schedule.job.name: schedule.interval_seconds
                for schedule in self._schedules
            },
        )

    def stop(self, timeout_seconds: float = 10.0) -> None:
        """Signal the thread to exit and wait for it (bounded by ``timeout_seconds``).

        Safe to call when not running. A tick in progress finishes its
        current job before the loop observes the stop event.
        """
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            logger.warning("job_scheduler_stop_timed_out", timeout=timeout_seconds)
        else:
            logger.info("job_scheduler_stopped")
        self._thread = None

    def run_all_once(self) -> None:
        """Run every registered job exactly once, synchronously, with
        failure containment.

        Exposed for tests and for operators who want an immediate sweep
        (e.g. right after enabling a job) without waiting an interval.
        """
        for schedule in self._schedules:
            self._run_contained(schedule.job)

    def _run_contained(self, job: Job) -> None:
        try:
            result = job.run()
        except Exception:
            # A failing job must never kill the scheduler: the next
            # interval retries it, and one job's failure must not starve
            # the others.
            logger.exception("job_run_failed", job=job.name)
        else:
            logger.info("job_run_completed", job=job.name, result=result)

    def _run_loop(self) -> None:
        if not self._schedules:
            return
        entries = [_Entry(schedule, time.monotonic()) for schedule in self._schedules]
        while True:
            wait = min(entry.next_due for entry in entries) - time.monotonic()
            # Event.wait doubles as the interruptible sleep: it returns
            # True (exit) the moment stop() sets the event, or False on
            # timeout (run whatever is due), so shutdown never waits out
            # a full interval.
            if self._stop_event.wait(max(wait, 0.0)):
                return
            now = time.monotonic()
            for entry in entries:
                if entry.next_due <= now:
                    self._run_contained(entry.schedule.job)
                    entry.next_due = time.monotonic() + entry.schedule.interval_seconds
