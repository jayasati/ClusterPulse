"""Unit tests for RetentionJob — full sweeps against a real (SQLite) schema."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.config import CollectorSettings
from collector.db.base import Base
from collector.db.models.alert import AlertModel
from collector.db.models.metric_sample import MetricSampleModel
from collector.db.models.remediation_action import RemediationActionModel
from collector.enums import RemediationActionStatus, RuleKind
from collector.jobs.retention import RetentionJob
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.metrics_repository import SqlAlchemyMetricsRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from collector.repositories.remediation_repository import (
    SqlAlchemyRemediationActionRepository,
)
from shared.constants import MetricType, Severity
from shared.contracts.v1.metrics import MetricSample
from shared.contracts.v1.remediation import PlaybookActionType

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


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


def _settings(**overrides) -> CollectorSettings:
    defaults = dict(
        retention_enabled=True,
        metrics_retention_days=7,
        resolved_alerts_retention_days=30,
        remediation_actions_retention_days=30,
        retention_batch_size=2,
    )
    defaults.update(overrides)
    return CollectorSettings(_env_file=None, api_tokens="t", **defaults)


def _seed(session_factory, *, days_old: int, with_audit_row: bool = True) -> None:
    """One node with a resolved alert, its audit row, and a metric sample —
    all ``days_old`` days before NOW."""
    at = NOW - timedelta(days=days_old)
    session = session_factory()
    try:
        SqlAlchemyNodeRepository(session).upsert_seen("node-1", at)
        SqlAlchemyMetricsRepository(session).bulk_insert(
            node_id="node-1",
            samples=[
                MetricSample(
                    metric_type=MetricType.CPU_USAGE_PERCENT, value=1.0, unit="percent"
                )
            ],
            collected_at=at,
            received_at=at,
        )
        alerts = SqlAlchemyAlertRepository(session)
        alert = alerts.create_alert(
            node_id="node-1",
            rule_key=f"rule:{days_old}",
            rule_kind=RuleKind.THRESHOLD,
            severity=Severity.WARNING,
            description="seeded",
            triggering_value=99.0,
            bound=85.0,
            fired_at=at,
        )
        alerts.resolve_alert(alert.id, at)
        if with_audit_row:
            SqlAlchemyRemediationActionRepository(session).create_action(
                node_id="node-1",
                alert_id=alert.id,
                rule_key=alert.rule_key,
                playbook_name="clear_reclaimable_tmp_directory",
                action_type=PlaybookActionType.CLEAR_DIRECTORY,
                parameters={},
                status=RemediationActionStatus.EXECUTED,
                reason=None,
                created_at=at,
            )
    finally:
        session.close()


def _count(session_factory, model) -> int:
    session = session_factory()
    try:
        return session.scalar(select(func.count()).select_from(model)) or 0
    finally:
        session.close()


def test_sweep_prunes_all_expired_tables_in_one_run(session_factory) -> None:
    """Audit rows are pruned before alerts within the same run, so an alert
    whose only reference expired alongside it is freed immediately — the
    FK-safe ordering, observable from the outside."""
    _seed(session_factory, days_old=60)
    _seed(session_factory, days_old=1)
    job = RetentionJob(session_factory, _settings(), now_fn=lambda: NOW)

    stats = job.run()

    assert stats.remediation_actions_deleted == 1
    assert stats.alerts_deleted == 1
    assert stats.metric_samples_deleted == 1
    assert _count(session_factory, RemediationActionModel) == 1
    assert _count(session_factory, AlertModel) == 1
    assert _count(session_factory, MetricSampleModel) == 1


def test_sweep_drains_backlogs_larger_than_one_batch(session_factory) -> None:
    for days_old in (40, 50, 60, 70, 80):
        _seed(session_factory, days_old=days_old)
    job = RetentionJob(session_factory, _settings(retention_batch_size=2), lambda: NOW)

    stats = job.run()

    assert stats.remediation_actions_deleted == 5
    assert stats.alerts_deleted == 5
    assert stats.metric_samples_deleted == 5
    assert _count(session_factory, MetricSampleModel) == 0


def test_sweep_on_fresh_data_deletes_nothing(session_factory) -> None:
    _seed(session_factory, days_old=1)
    job = RetentionJob(session_factory, _settings(), now_fn=lambda: NOW)

    stats = job.run()

    assert stats.remediation_actions_deleted == 0
    assert stats.alerts_deleted == 0
    assert stats.metric_samples_deleted == 0


def test_sweep_respects_distinct_windows_per_table(session_factory) -> None:
    """10-day-old data: samples (7d window) expire; alerts and audit rows
    (30d windows) survive."""
    _seed(session_factory, days_old=10)
    job = RetentionJob(session_factory, _settings(), now_fn=lambda: NOW)

    stats = job.run()

    assert stats.metric_samples_deleted == 1
    assert stats.alerts_deleted == 0
    assert stats.remediation_actions_deleted == 0


def test_sweep_is_idempotent(session_factory) -> None:
    _seed(session_factory, days_old=60)
    job = RetentionJob(session_factory, _settings(), now_fn=lambda: NOW)

    first = job.run()
    second = job.run()

    assert first.metric_samples_deleted == 1
    assert second == type(second)(0, 0, 0)
