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

from collector.repositories.metrics_repository import SqlAlchemyMetricsRepository
from collector.repositories.node_repository import SqlAlchemyNodeRepository
from shared.constants import MetricType
from shared.contracts.v1.metrics import MetricSample


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
