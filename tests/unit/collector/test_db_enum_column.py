"""Regression test for the enum-storage bug found via live Postgres testing.

SQLAlchemy's ``Enum(SomeEnumClass)`` defaults to storing each member's
``.name`` (e.g. ``"CPU_USAGE_PERCENT"``), not its ``.value`` (e.g.
``"cpu.usage_percent"``). Every Alembic migration in this project defines
the Postgres enum type's labels from ``.value`` — so without
``str_enum_column`` (``values_callable``), inserts succeed silently
against SQLite (whose ``create_all()``-generated CHECK constraint uses
the same, equally-wrong default, making the bug self-consistent there)
but fail against a real Postgres with
``invalid input value for enum ...: "CPU_USAGE_PERCENT"``. This test
asserts against the *raw stored text*, bypassing the ORM's own
deserialization, so a regression back to the buggy default would fail
here even on SQLite.
"""

from datetime import datetime, timezone

from sqlalchemy import text

from collector.enums import RemediationActionStatus, RuleKind
from collector.repositories.alert_repository import SqlAlchemyAlertRepository
from collector.repositories.metrics_repository import SqlAlchemyMetricsRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from collector.repositories.remediation_repository import (
    SqlAlchemyRemediationActionRepository,
)
from shared.constants import MetricType, Severity
from shared.contracts.v1.metrics import MetricSample
from shared.contracts.v1.remediation import PlaybookActionType


def test_metric_type_is_stored_as_its_value_not_its_name(db_session) -> None:
    now = datetime.now(timezone.utc)
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", now)
    SqlAlchemyMetricsRepository(db_session).bulk_insert(
        node_id="node-1",
        samples=[
            MetricSample(
                metric_type=MetricType.CPU_USAGE_PERCENT, value=1.0, unit="percent"
            )
        ],
        collected_at=now,
        received_at=now,
    )

    raw_value = db_session.execute(
        text("SELECT metric_type FROM metric_samples LIMIT 1")
    ).scalar_one()

    assert raw_value == "cpu.usage_percent"
    assert raw_value != "CPU_USAGE_PERCENT"


def test_remediation_action_type_and_status_are_stored_as_their_values(
    db_session,
) -> None:
    now = datetime.now(timezone.utc)
    SqlAlchemyNodeRepository(db_session).upsert_seen("node-1", now)
    alert = SqlAlchemyAlertRepository(db_session).create_alert(
        node_id="node-1",
        rule_key="threshold:disk.usage_percent",
        rule_kind=RuleKind.THRESHOLD,
        severity=Severity.WARNING,
        description="disk too full",
        triggering_value=95.0,
        bound=85.0,
        fired_at=now,
    )
    SqlAlchemyRemediationActionRepository(db_session).create_action(
        node_id="node-1",
        alert_id=alert.id,
        rule_key="threshold:disk.usage_percent",
        playbook_name="clear_tmp",
        action_type=PlaybookActionType.CLEAR_DIRECTORY,
        parameters={"path": "/tmp/reclaimable"},
        status=RemediationActionStatus.DISPATCHED,
        reason=None,
        created_at=now,
    )

    row = db_session.execute(
        text("SELECT action_type, status FROM remediation_actions LIMIT 1")
    ).one()

    assert row.action_type == "clear_directory"
    assert row.action_type != "CLEAR_DIRECTORY"
    assert row.status == "dispatched"
    assert row.status != "DISPATCHED"
