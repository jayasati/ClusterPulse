"""The remediation reconciliation job: time out unanswered dispatches.

A remediation action stuck at ``DISPATCHED`` means the Agent crashed, was
partitioned between dispatch and result-report, or silently dropped its
report (result reports are not buffered/retried — see
``docs/adr/020-remediation-dispatch-mechanism.md``). Until Phase 7 such a
row stayed ``DISPATCHED`` forever. This job closes the loop: dispatches
older than the timeout are marked ``FAILED`` with an explicit
timed-out reason, so the audit log always converges to a terminal answer
(and retention, which deliberately never prunes ``DISPATCHED`` rows, can
eventually reclaim them).

If an Agent's result report arrives *after* the timeout marked the row
``FAILED``, the report still overwrites it — the Agent observed the
actual execution; the timeout is only the Collector's inference. See
``docs/adr/022-staleness-reconciliation-jobs.md``.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable

import structlog
from sqlalchemy.orm import Session, sessionmaker

from collector.config import CollectorSettings
from collector.enums import RemediationActionStatus
from collector.repositories.remediation_repository import (
    SqlAlchemyRemediationActionRepository,
)

logger = structlog.get_logger(__name__)

TIMED_OUT_REASON = (
    "dispatch timed out — Agent never reported a result "
    "(crash or partition between dispatch and result-report)"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReconciliationJob:
    """Marks over-age ``DISPATCHED`` remediation actions as ``FAILED``."""

    name = "remediation_reconciliation"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: CollectorSettings,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._timeout_seconds = settings.remediation_dispatch_timeout_seconds
        self._now_fn = now_fn

    def run(self) -> dict[str, int]:
        """One sweep. Returns the count of dispatches timed out."""
        now = self._now_fn()
        cutoff = now - timedelta(seconds=self._timeout_seconds)
        session = self._session_factory()
        timed_out = 0
        try:
            repo = SqlAlchemyRemediationActionRepository(session)
            for action in repo.list_dispatched_before(cutoff):
                repo.mark_result(
                    action.id,
                    status=RemediationActionStatus.FAILED,
                    reason=TIMED_OUT_REASON,
                    completed_at=now,
                )
                timed_out += 1
                logger.warning(
                    "remediation_dispatch_timed_out",
                    action_id=action.id,
                    node_id=action.node_id,
                    playbook_name=action.playbook_name,
                    dispatched_at=action.created_at.isoformat(),
                )
        finally:
            session.close()
        return {"timed_out": timed_out}
