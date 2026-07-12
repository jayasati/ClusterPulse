"""Background jobs run inside the Collector process.

The Collector had no background execution at all before Phase 6 — every
behavior was request-triggered (see the "ingestion-triggered only"
limitations in ``docs/adr/006-alert-lifecycle.md``). This package holds
the thread-based periodic scheduler (``scheduler.py``) and its jobs:
data retention (``retention.py`` — ADR-010), staleness alerting
(``staleness.py``) and remediation-dispatch reconciliation
(``reconciliation.py``) — both ADR-022.
"""

from collector.jobs.reconciliation import ReconciliationJob
from collector.jobs.retention import RetentionJob, RetentionRunStats
from collector.jobs.scheduler import Job, JobSchedule, PeriodicJobScheduler
from collector.jobs.staleness import StalenessJob

__all__ = [
    "Job",
    "JobSchedule",
    "PeriodicJobScheduler",
    "ReconciliationJob",
    "RetentionJob",
    "RetentionRunStats",
    "StalenessJob",
]
