"""The data-retention job: bounded, FK-safe pruning of aged rows.

Tables are pruned oldest-first in foreign-key-safe order:

1. ``remediation_actions`` (terminal rows only) — the referencing side
2. ``alerts`` (resolved only, and only once no audit row references them)
3. ``metric_samples`` — the bulk of the data, pruned last

Each table is drained in ``batch_size``-bounded DELETE transactions, so an
arbitrarily large backlog (e.g. retention enabled months after deploy)
never takes long locks or builds one giant transaction — and an interrupt
mid-run (shutdown, crash, DB outage) loses nothing: every committed batch
stays deleted, and the next run continues from wherever this one stopped.

See ``docs/adr/010-retention-policy.md``.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import structlog
from sqlalchemy.orm import Session, sessionmaker

from collector.config import CollectorSettings
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.metrics_repository import SqlAlchemyMetricsRepository
from collector.repositories.remediation_repository import (
    SqlAlchemyRemediationActionRepository,
)

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RetentionRunStats:
    """What one retention sweep deleted, per table."""

    remediation_actions_deleted: int
    alerts_deleted: int
    metric_samples_deleted: int


class RetentionJob:
    """Prunes aged rows per the retention windows in ``CollectorSettings``.

    Owns a session per run (never a long-lived one): the job runs on the
    scheduler thread, and SQLAlchemy sessions are not thread-safe to share
    with the request path.
    """

    name = "retention"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: CollectorSettings,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._now_fn = now_fn

    def run(self) -> RetentionRunStats:
        """Execute one full sweep and return per-table deletion counts."""
        now = self._now_fn()
        batch_size = self._settings.retention_batch_size
        session = self._session_factory()
        try:
            actions_deleted = self._drain(
                SqlAlchemyRemediationActionRepository(session).prune_terminal_before,
                now - timedelta(days=self._settings.remediation_actions_retention_days),
                batch_size,
            )
            alerts_deleted = self._drain(
                SqlAlchemyAlertRepository(session).prune_resolved_before,
                now - timedelta(days=self._settings.resolved_alerts_retention_days),
                batch_size,
            )
            samples_deleted = self._drain(
                SqlAlchemyMetricsRepository(session).prune_samples_before,
                now - timedelta(days=self._settings.metrics_retention_days),
                batch_size,
            )
        finally:
            session.close()
        stats = RetentionRunStats(
            remediation_actions_deleted=actions_deleted,
            alerts_deleted=alerts_deleted,
            metric_samples_deleted=samples_deleted,
        )
        logger.info(
            "retention_sweep_completed",
            remediation_actions_deleted=stats.remediation_actions_deleted,
            alerts_deleted=stats.alerts_deleted,
            metric_samples_deleted=stats.metric_samples_deleted,
        )
        return stats

    @staticmethod
    def _drain(
        prune: Callable[[datetime, int], int], cutoff: datetime, batch_size: int
    ) -> int:
        """Call ``prune`` until it reports no more rows; return the total."""
        total = 0
        while (deleted := prune(cutoff, batch_size)) > 0:
            total += deleted
        return total
