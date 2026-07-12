"""Background jobs run inside the Collector process.

The Collector had no background execution at all before Phase 6 — every
behavior was request-triggered (see the "ingestion-triggered only"
limitations in ``docs/adr/006-alert-lifecycle.md``). This package
introduces the first scheduled work: a deliberately small, thread-based
periodic scheduler (``scheduler.py``) and the data-retention job it runs
(``retention.py``). See ``docs/adr/010-retention-policy.md``.
"""

from collector.jobs.retention import RetentionJob, RetentionRunStats
from collector.jobs.scheduler import Job, PeriodicJobScheduler

__all__ = ["Job", "PeriodicJobScheduler", "RetentionJob", "RetentionRunStats"]
