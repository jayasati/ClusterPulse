"""Unit tests for the retention prune methods on all three repositories.

Every test seeds via the repositories' own public APIs (never raw SQL), so
the prune behavior under test is exactly what production data would see.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from collector.db.models.alert import AlertModel
from collector.db.models.metric_sample import MetricSampleModel
from collector.db.models.remediation_action import RemediationActionModel
from collector.enums import AlertStatus, RemediationActionStatus, RuleKind
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
CUTOFF = NOW - timedelta(days=7)


def _sample() -> MetricSample:
    return MetricSample(
        metric_type=MetricType.CPU_USAGE_PERCENT, value=1.0, unit="percent"
    )


def _seed_node(db_session, node_id: str = "node-1") -> None:
    SqlAlchemyNodeRepository(db_session).upsert_seen(node_id, NOW)


def _seed_samples(db_session, *received_ats: datetime) -> None:
    repo = SqlAlchemyMetricsRepository(db_session)
    for received_at in received_ats:
        repo.bulk_insert(
            node_id="node-1",
            samples=[_sample()],
            collected_at=received_at,
            received_at=received_at,
        )


def _seed_alert(db_session, *, resolved_at: datetime | None, rule_key: str):
    repo = SqlAlchemyAlertRepository(db_session)
    alert = repo.create_alert(
        node_id="node-1",
        rule_key=rule_key,
        rule_kind=RuleKind.THRESHOLD,
        severity=Severity.WARNING,
        description="test alert",
        triggering_value=99.0,
        bound=85.0,
        fired_at=CUTOFF - timedelta(days=30),
    )
    if resolved_at is not None:
        alert = repo.resolve_alert(alert.id, resolved_at)
    return alert


def _seed_action(
    db_session,
    alert_id: int,
    status: RemediationActionStatus,
    created_at: datetime,
):
    return SqlAlchemyRemediationActionRepository(db_session).create_action(
        node_id="node-1",
        alert_id=alert_id,
        rule_key="threshold:disk.usage_percent",
        playbook_name="clear_reclaimable_tmp_directory",
        action_type=PlaybookActionType.CLEAR_DIRECTORY,
        parameters={"path": "/tmp/x"},
        status=status,
        reason=None,
        created_at=created_at,
    )


# --- metric samples -------------------------------------------------------


def test_prune_samples_deletes_only_rows_older_than_cutoff(db_session) -> None:
    _seed_node(db_session)
    _seed_samples(db_session, CUTOFF - timedelta(hours=1), CUTOFF + timedelta(hours=1))

    deleted = SqlAlchemyMetricsRepository(db_session).prune_samples_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 1
    survivors = db_session.scalars(select(MetricSampleModel)).all()
    assert len(survivors) == 1


def test_prune_samples_exactly_at_cutoff_survives(db_session) -> None:
    """The comparison is strict (< cutoff) — a boundary row is retained."""
    _seed_node(db_session)
    _seed_samples(db_session, CUTOFF)

    deleted = SqlAlchemyMetricsRepository(db_session).prune_samples_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 0


def test_prune_samples_respects_batch_size(db_session) -> None:
    _seed_node(db_session)
    _seed_samples(db_session, *[CUTOFF - timedelta(hours=i + 1) for i in range(5)])
    repo = SqlAlchemyMetricsRepository(db_session)

    first = repo.prune_samples_before(CUTOFF, batch_size=2)
    remaining = len(db_session.scalars(select(MetricSampleModel)).all())

    assert first == 2
    assert remaining == 3


def test_prune_samples_repeated_calls_drain_to_zero(db_session) -> None:
    _seed_node(db_session)
    _seed_samples(db_session, *[CUTOFF - timedelta(hours=i + 1) for i in range(5)])
    repo = SqlAlchemyMetricsRepository(db_session)

    total = 0
    while (deleted := repo.prune_samples_before(CUTOFF, batch_size=2)) > 0:
        total += deleted

    assert total == 5
    assert db_session.scalars(select(MetricSampleModel)).all() == []


def test_prune_samples_on_empty_table_returns_zero(db_session) -> None:
    assert (
        SqlAlchemyMetricsRepository(db_session).prune_samples_before(
            CUTOFF, batch_size=100
        )
        == 0
    )


# --- alerts ---------------------------------------------------------------


def test_prune_alerts_deletes_only_old_resolved_alerts(db_session) -> None:
    _seed_node(db_session)
    _seed_alert(db_session, resolved_at=CUTOFF - timedelta(days=1), rule_key="rule:old")
    _seed_alert(
        db_session, resolved_at=CUTOFF + timedelta(days=1), rule_key="rule:recent"
    )

    deleted = SqlAlchemyAlertRepository(db_session).prune_resolved_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 1
    survivor = db_session.scalars(select(AlertModel)).one()
    assert survivor.rule_key == "rule:recent"


def test_prune_alerts_never_touches_firing_alerts(db_session) -> None:
    """A firing alert is live state, not history — age is irrelevant."""
    _seed_node(db_session)
    _seed_alert(db_session, resolved_at=None, rule_key="rule:ancient-firing")

    deleted = SqlAlchemyAlertRepository(db_session).prune_resolved_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 0
    assert db_session.scalars(select(AlertModel)).one().status == AlertStatus.FIRING


def test_prune_alerts_skips_alerts_still_referenced_by_audit_rows(db_session) -> None:
    """FK safety: the audit row owns the reference; the alert waits."""
    _seed_node(db_session)
    alert = _seed_alert(
        db_session, resolved_at=CUTOFF - timedelta(days=1), rule_key="rule:referenced"
    )
    _seed_action(
        db_session,
        alert.id,
        RemediationActionStatus.EXECUTED,
        created_at=CUTOFF - timedelta(days=1),
    )

    deleted = SqlAlchemyAlertRepository(db_session).prune_resolved_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 0
    assert len(db_session.scalars(select(AlertModel)).all()) == 1


def test_prune_alerts_prunable_once_referencing_audit_rows_are_gone(db_session) -> None:
    _seed_node(db_session)
    alert = _seed_alert(
        db_session, resolved_at=CUTOFF - timedelta(days=1), rule_key="rule:freed"
    )
    _seed_action(
        db_session,
        alert.id,
        RemediationActionStatus.EXECUTED,
        created_at=CUTOFF - timedelta(days=1),
    )

    actions_deleted = SqlAlchemyRemediationActionRepository(
        db_session
    ).prune_terminal_before(CUTOFF, batch_size=100)
    alerts_deleted = SqlAlchemyAlertRepository(db_session).prune_resolved_before(
        CUTOFF, batch_size=100
    )

    assert actions_deleted == 1
    assert alerts_deleted == 1
    assert db_session.scalars(select(AlertModel)).all() == []


# --- remediation actions --------------------------------------------------


def test_prune_actions_deletes_old_terminal_rows(db_session) -> None:
    _seed_node(db_session)
    alert = _seed_alert(db_session, resolved_at=None, rule_key="rule:r")
    _seed_action(
        db_session,
        alert.id,
        RemediationActionStatus.EXECUTED,
        created_at=CUTOFF - timedelta(days=1),
    )
    _seed_action(
        db_session,
        alert.id,
        RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT,
        created_at=CUTOFF - timedelta(days=2),
    )
    _seed_action(
        db_session,
        alert.id,
        RemediationActionStatus.FAILED,
        created_at=CUTOFF + timedelta(days=1),
    )

    deleted = SqlAlchemyRemediationActionRepository(db_session).prune_terminal_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 2
    survivor = db_session.scalars(select(RemediationActionModel)).one()
    assert survivor.status == RemediationActionStatus.FAILED


def test_prune_actions_never_touches_dispatched_rows(db_session) -> None:
    """A DISPATCHED row is an unresolved question, not prunable history."""
    _seed_node(db_session)
    alert = _seed_alert(db_session, resolved_at=None, rule_key="rule:r")
    _seed_action(
        db_session,
        alert.id,
        RemediationActionStatus.DISPATCHED,
        created_at=CUTOFF - timedelta(days=365),
    )

    deleted = SqlAlchemyRemediationActionRepository(db_session).prune_terminal_before(
        CUTOFF, batch_size=100
    )

    assert deleted == 0
    assert len(db_session.scalars(select(RemediationActionModel)).all()) == 1
