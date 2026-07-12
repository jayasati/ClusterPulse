"""The staleness-alerting job: the dead-man switch, finally acting.

``NodeRegistryService`` has computed ``is_stale`` since Phase 2, but until
Phase 7 nothing ever *acted* on it — a node that died silently produced no
alert, ever, because all rule evaluation is ingestion-triggered
(``docs/adr/006-alert-lifecycle.md``). This job closes that gap: on every
tick it opens a ``staleness:node_heartbeat`` alert for each silent node
and resolves it when the node pushes again, reusing the entire existing
alert lifecycle (dedup, read API, dashboards, Telegram) rather than
inventing a parallel mechanism.

Startup grace: the first tick after process start observes and remembers,
but never opens alerts. After a *Collector* outage every node in the
fleet looks stale at once — alerting on all of them would misattribute
our own downtime to the fleet. Nodes that are genuinely dead are caught
one interval later.

See ``docs/adr/022-staleness-reconciliation-jobs.md``.
"""

from datetime import datetime, timezone
from typing import Callable

import structlog
from sqlalchemy.orm import Session, sessionmaker

from collector.config import CollectorSettings
from collector.enums import RuleKind
from collector.notifications import formatting
from collector.notifications.protocols import Notifier
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from shared.constants import Severity

logger = structlog.get_logger(__name__)

STALENESS_RULE_KEY = "staleness:node_heartbeat"
"""Reserved rule_key namespace — not produced by the config-file rule
engine, so it can never collide with a configured rule."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StalenessJob:
    """Opens/resolves staleness alerts for silent/recovered nodes."""

    name = "staleness"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: CollectorSettings,
        notifier: Notifier | None,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._stale_after_seconds = settings.heartbeat_stale_after_seconds
        self._notifier = notifier
        self._now_fn = now_fn
        self._first_run_done = False

    def run(self) -> dict[str, int]:
        """One sweep. Returns counts for logging: opened/resolved/stale."""
        now = self._now_fn()
        session = self._session_factory()
        opened = resolved = stale_count = 0
        try:
            nodes = SqlAlchemyNodeRepository(session).list_all()
            alerts = SqlAlchemyAlertRepository(session)
            for node in nodes:
                silent_seconds = (now - node.last_seen_at).total_seconds()
                is_stale = silent_seconds >= self._stale_after_seconds
                open_alert = alerts.find_open_alert(node.node_id, STALENESS_RULE_KEY)
                if is_stale:
                    stale_count += 1
                    if open_alert is None and self._first_run_done:
                        record = alerts.create_alert(
                            node_id=node.node_id,
                            rule_key=STALENESS_RULE_KEY,
                            rule_kind=RuleKind.STALENESS,
                            severity=Severity.CRITICAL,
                            description=(
                                "Node has stopped reporting (no metrics or "
                                f"heartbeat for {int(silent_seconds)}s)"
                            ),
                            triggering_value=silent_seconds,
                            bound=self._stale_after_seconds,
                            fired_at=now,
                        )
                        opened += 1
                        logger.warning(
                            "staleness_alert_opened",
                            node_id=node.node_id,
                            silent_seconds=int(silent_seconds),
                        )
                        self._notify(formatting.format_opened(record))
                elif open_alert is not None:
                    record = alerts.resolve_alert(open_alert.id, resolved_at=now)
                    resolved += 1
                    logger.info("staleness_alert_resolved", node_id=node.node_id)
                    self._notify(formatting.format_resolved(record))
        finally:
            session.close()
        self._first_run_done = True
        return {"stale": stale_count, "opened": opened, "resolved": resolved}

    def _notify(self, message: str) -> None:
        if self._notifier is not None:
            self._notifier.notify(message)
