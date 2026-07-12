"""Unit tests for StalenessJob — the dead-man switch acting on is_stale."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.config import CollectorSettings
from collector.db.base import Base
from collector.enums import AlertStatus, RuleKind
from collector.jobs.staleness import STALENESS_RULE_KEY, StalenessJob
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from shared.constants import Severity

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)
STALE_AFTER = 90.0


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> bool:
        self.messages.append(message)
        return True


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _settings() -> CollectorSettings:
    return CollectorSettings(
        _env_file=None,
        api_tokens="t",
        staleness_alerting_enabled=True,
        heartbeat_stale_after_seconds=STALE_AFTER,
    )


def _seed_node(session_factory, node_id: str, last_seen_at: datetime) -> None:
    session = session_factory()
    try:
        SqlAlchemyNodeRepository(session).upsert_seen(node_id, last_seen_at)
    finally:
        session.close()


def _alerts(session_factory, status: AlertStatus | None = None):
    session = session_factory()
    try:
        return SqlAlchemyAlertRepository(session).list_alerts(status)
    finally:
        session.close()


def _warmed_job(session_factory, notifier=None) -> StalenessJob:
    """A job whose startup grace period has already elapsed."""
    job = StalenessJob(session_factory, _settings(), notifier, now_fn=lambda: NOW)
    job._first_run_done = True
    return job


def test_first_run_observes_but_does_not_alert(session_factory) -> None:
    """Startup grace: after a Collector outage the whole fleet looks stale
    at once — the first sweep must observe, not accuse."""
    _seed_node(session_factory, "silent-node", NOW - timedelta(hours=2))
    notifier = RecordingNotifier()
    job = StalenessJob(session_factory, _settings(), notifier, now_fn=lambda: NOW)

    stats = job.run()

    assert stats == {"stale": 1, "opened": 0, "resolved": 0}
    assert _alerts(session_factory) == []
    assert notifier.messages == []


def test_second_run_opens_alert_for_still_stale_node(session_factory) -> None:
    _seed_node(session_factory, "silent-node", NOW - timedelta(seconds=300))
    notifier = RecordingNotifier()
    job = StalenessJob(session_factory, _settings(), notifier, now_fn=lambda: NOW)

    job.run()
    stats = job.run()

    assert stats["opened"] == 1
    (alert,) = _alerts(session_factory)
    assert alert.rule_key == STALENESS_RULE_KEY
    assert alert.rule_kind == RuleKind.STALENESS
    assert alert.severity == Severity.CRITICAL
    assert alert.status == AlertStatus.FIRING
    assert alert.triggering_value == pytest.approx(300.0)
    assert alert.bound == STALE_AFTER
    assert len(notifier.messages) == 1
    assert "silent-node" in notifier.messages[0]


def test_fresh_node_gets_no_alert(session_factory) -> None:
    _seed_node(session_factory, "healthy-node", NOW - timedelta(seconds=10))
    job = _warmed_job(session_factory)

    stats = job.run()

    assert stats == {"stale": 0, "opened": 0, "resolved": 0}
    assert _alerts(session_factory) == []


def test_open_staleness_alert_is_not_duplicated(session_factory) -> None:
    """Repeated sweeps over a still-silent node keep exactly one open alert
    — the (node_id, rule_key) dedup of the normal lifecycle."""
    _seed_node(session_factory, "silent-node", NOW - timedelta(hours=1))
    job = _warmed_job(session_factory)

    job.run()
    job.run()
    job.run()

    assert len(_alerts(session_factory)) == 1


def test_alert_resolves_and_notifies_when_node_recovers(session_factory) -> None:
    _seed_node(session_factory, "flaky-node", NOW - timedelta(hours=1))
    notifier = RecordingNotifier()
    job = _warmed_job(session_factory, notifier)
    job.run()

    _seed_node(session_factory, "flaky-node", NOW)  # node pushes again
    stats = job.run()

    assert stats["resolved"] == 1
    (alert,) = _alerts(session_factory)
    assert alert.status == AlertStatus.RESOLVED
    assert alert.resolved_at == NOW
    assert len(notifier.messages) == 2
    assert "RESOLVED" in notifier.messages[1]


def test_exactly_at_boundary_counts_as_stale(session_factory) -> None:
    """>= stale_after is stale — mirrors NodeRegistryService's is_stale."""
    _seed_node(session_factory, "edge-node", NOW - timedelta(seconds=STALE_AFTER))
    job = _warmed_job(session_factory)

    stats = job.run()

    assert stats["stale"] == 1


def test_works_without_a_notifier(session_factory) -> None:
    _seed_node(session_factory, "silent-node", NOW - timedelta(hours=1))
    job = _warmed_job(session_factory, notifier=None)

    stats = job.run()  # must not raise

    assert stats["opened"] == 1
