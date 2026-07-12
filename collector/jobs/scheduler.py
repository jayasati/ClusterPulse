"""A minimal thread-based periodic job scheduler.

A daemon thread wakes every ``interval_seconds`` and runs each registered
job in sequence. A thread (not an asyncio task) is deliberate: the
Collector's entire persistence stack is synchronous SQLAlchemy
(``docs/adr/017-collector-sync-vs-async-db.md``), so jobs block on I/O —
exactly what a worker thread is for, and exactly what would stall the
event loop if scheduled there.

Failure containment: a job raising is *contained* — logged with its name,
the remaining jobs still run, and the loop continues. The thread can only
exit via ``stop()``. Overlapping runs are impossible by construction:
one thread runs all jobs sequentially, and the next tick's wait doesn't
begin until the current tick's jobs finish.
"""

import threading
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


class PeriodicJobScheduler:
    """Runs a fixed set of jobs every ``interval_seconds`` on a daemon thread.

    The first run happens one full interval after ``start()`` — startup is
    already the Collector's busiest moment (migrations just ran, agents
    reconnect and drain buffers), so deferring the first sweep keeps boot
    predictable.
    """

    def __init__(self, interval_seconds: float, jobs: Sequence[Job]) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._interval_seconds = interval_seconds
        self._jobs = list(jobs)
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
            interval_seconds=self._interval_seconds,
            jobs=[job.name for job in self._jobs],
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

    def run_pending_once(self) -> None:
        """Run every job exactly once, synchronously, with failure containment.

        Exposed for tests and for operators who want an immediate sweep
        (e.g. right after enabling retention) without waiting an interval.
        """
        for job in self._jobs:
            try:
                result = job.run()
            except Exception:
                # A failing job must never kill the scheduler: the next
                # interval retries it, and one job's failure must not
                # starve the others.
                logger.exception("job_run_failed", job=job.name)
            else:
                logger.info("job_run_completed", job=job.name, result=result)

    def _run_loop(self) -> None:
        # Event.wait doubles as the interruptible sleep: it returns True
        # (exit) the moment stop() sets the event, or False on timeout
        # (run the tick), so shutdown never waits out a full interval.
        while not self._stop_event.wait(self._interval_seconds):
            self.run_pending_once()
