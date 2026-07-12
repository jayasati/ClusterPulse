"""Unit tests for ReconciliationJob — timing out unanswered dispatches."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.config import CollectorSettings
from collector.db.base import Base
from collector.enums import RemediationActionStatus, RuleKind
from collector.jobs.reconciliation import TIMED_OUT_REASON, ReconciliationJob
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from collector.repositories.remediation_repository import (
    SqlAlchemyRemediationActionRepository,
)
from shared.constants import Severity
from shared.contracts.v1.remediation import PlaybookActionType

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)
TIMEOUT = 1800.0


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
        remediation_reconciliation_enabled=True,
        remediation_dispatch_timeout_seconds=TIMEOUT,
    )


def _seed_action(session_factory, status: RemediationActionStatus, age_seconds: float):
    session = session_factory()
    try:
        SqlAlchemyNodeRepository(session).upsert_seen("node-1", NOW)
        alert = SqlAlchemyAlertRepository(session).create_alert(
            node_id="node-1",
            rule_key="threshold:disk.usage_percent",
            rule_kind=RuleKind.THRESHOLD,
            severity=Severity.WARNING,
            description="seeded",
            triggering_value=99.0,
            bound=85.0,
            fired_at=NOW - timedelta(seconds=age_seconds),
        )
        return SqlAlchemyRemediationActionRepository(session).create_action(
            node_id="node-1",
            alert_id=alert.id,
            rule_key=alert.rule_key,
            playbook_name="clear_reclaimable_tmp_directory",
            action_type=PlaybookActionType.CLEAR_DIRECTORY,
            parameters={},
            status=status,
            reason=None,
            created_at=NOW - timedelta(seconds=age_seconds),
        )
    finally:
        session.close()


def _get_action(session_factory, action_id: int):
    session = session_factory()
    try:
        return SqlAlchemyRemediationActionRepository(session).get(action_id)
    finally:
        session.close()


def test_over_age_dispatched_action_is_marked_failed(session_factory) -> None:
    action = _seed_action(
        session_factory, RemediationActionStatus.DISPATCHED, age_seconds=TIMEOUT + 60
    )
    job = ReconciliationJob(session_factory, _settings(), now_fn=lambda: NOW)

    stats = job.run()

    assert stats == {"timed_out": 1}
    updated = _get_action(session_factory, action.id)
    assert updated is not None
    assert updated.status == RemediationActionStatus.FAILED
    assert updated.reason == TIMED_OUT_REASON
    assert updated.completed_at == NOW


def test_recent_dispatched_action_is_left_alone(session_factory) -> None:
    action = _seed_action(
        session_factory, RemediationActionStatus.DISPATCHED, age_seconds=60
    )
    job = ReconciliationJob(session_factory, _settings(), now_fn=lambda: NOW)

    stats = job.run()

    assert stats == {"timed_out": 0}
    updated = _get_action(session_factory, action.id)
    assert updated is not None
    assert updated.status == RemediationActionStatus.DISPATCHED


def test_terminal_actions_are_never_touched(session_factory) -> None:
    for status in (
        RemediationActionStatus.EXECUTED,
        RemediationActionStatus.FAILED,
        RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT,
    ):
        _seed_action(session_factory, status, age_seconds=TIMEOUT * 10)
    job = ReconciliationJob(session_factory, _settings(), now_fn=lambda: NOW)

    stats = job.run()

    assert stats == {"timed_out": 0}


def test_late_agent_result_overwrites_the_timeout_verdict(session_factory) -> None:
    """The Agent observed the actual execution; the timeout is only the
    Collector's inference — ground truth wins, even arriving late."""
    action = _seed_action(
        session_factory, RemediationActionStatus.DISPATCHED, age_seconds=TIMEOUT + 60
    )
    job = ReconciliationJob(session_factory, _settings(), now_fn=lambda: NOW)
    job.run()

    session = session_factory()
    try:
        late = SqlAlchemyRemediationActionRepository(session).mark_result(
            action.id,
            status=RemediationActionStatus.EXECUTED,
            reason="removed 3 entries",
            completed_at=NOW + timedelta(seconds=30),
        )
    finally:
        session.close()

    assert late.status == RemediationActionStatus.EXECUTED
    assert late.reason == "removed 3 entries"


def test_sweep_is_idempotent(session_factory) -> None:
    _seed_action(
        session_factory, RemediationActionStatus.DISPATCHED, age_seconds=TIMEOUT + 60
    )
    job = ReconciliationJob(session_factory, _settings(), now_fn=lambda: NOW)

    first = job.run()
    second = job.run()

    assert first == {"timed_out": 1}
    assert second == {"timed_out": 0}
