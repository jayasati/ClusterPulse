"""SQLAlchemy-backed ``AlertRepository`` implementation."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from collector.db.models.alert import AlertModel
from collector.db.timeutil import ensure_utc
from collector.enums import AlertStatus, RuleKind
from collector.repositories.protocols import AlertRecord
from shared.constants import Severity
from shared.exceptions import PersistenceError


class SqlAlchemyAlertRepository:
    """Persists alerts and their lifecycle transitions via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_open_alert(self, node_id: str, rule_key: str) -> AlertRecord | None:
        """Return the currently-firing alert for ``(node_id, rule_key)``, if any."""
        statement = select(AlertModel).where(
            AlertModel.node_id == node_id,
            AlertModel.rule_key == rule_key,
            AlertModel.status == AlertStatus.FIRING,
        )
        try:
            row = self._session.scalars(statement).first()
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to look up open alert",
                context={"node_id": node_id, "rule_key": rule_key},
            ) from exc
        return _to_record(row) if row is not None else None

    def create_alert(
        self,
        node_id: str,
        rule_key: str,
        rule_kind: RuleKind,
        severity: Severity,
        description: str,
        triggering_value: float,
        bound: float,
        fired_at: datetime,
    ) -> AlertRecord:
        """Open a new alert in the ``firing`` state."""
        row = AlertModel(
            node_id=node_id,
            rule_key=rule_key,
            rule_kind=rule_kind,
            severity=severity,
            status=AlertStatus.FIRING,
            description=description,
            triggering_value=triggering_value,
            bound=bound,
            first_fired_at=fired_at,
            last_fired_at=fired_at,
            resolved_at=None,
        )
        try:
            self._session.add(row)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                "failed to create alert",
                context={"node_id": node_id, "rule_key": rule_key},
            ) from exc
        return _to_record(row)

    def update_last_fired(
        self, alert_id: int, triggering_value: float, fired_at: datetime
    ) -> AlertRecord:
        """Advance an already-firing alert's ``last_fired_at``/``triggering_value``."""
        row = self._get_or_raise(alert_id, "failed to advance alert")
        row.triggering_value = triggering_value
        row.last_fired_at = fired_at
        return self._commit_and_return(row, alert_id, "failed to advance alert")

    def resolve_alert(self, alert_id: int, resolved_at: datetime) -> AlertRecord:
        """Transition an alert from ``firing`` to ``resolved``."""
        row = self._get_or_raise(alert_id, "failed to resolve alert")
        row.status = AlertStatus.RESOLVED
        row.resolved_at = resolved_at
        return self._commit_and_return(row, alert_id, "failed to resolve alert")

    def acknowledge_alert(
        self, alert_id: int, acknowledged_by: str, acknowledged_at: datetime
    ) -> AlertRecord:
        """Set acknowledgement info on an alert. Idempotent while firing."""
        row = self._get_or_raise(alert_id, "failed to acknowledge alert")
        row.acknowledged_by = acknowledged_by
        row.acknowledged_at = acknowledged_at
        return self._commit_and_return(row, alert_id, "failed to acknowledge alert")

    def escalate_alert(self, alert_id: int, escalated_at: datetime) -> AlertRecord:
        """Mark an alert as escalated."""
        row = self._get_or_raise(alert_id, "failed to escalate alert")
        row.escalated_at = escalated_at
        return self._commit_and_return(row, alert_id, "failed to escalate alert")

    def get(self, alert_id: int) -> AlertRecord | None:
        """Return the alert with ``alert_id``, or ``None`` if unknown."""
        try:
            row = self._session.get(AlertModel, alert_id)
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to fetch alert", context={"alert_id": alert_id}
            ) from exc
        return _to_record(row) if row is not None else None

    def list_alerts(self, status: AlertStatus | None = None) -> list[AlertRecord]:
        """Return every alert, optionally filtered to a single ``status``."""
        statement = select(AlertModel)
        if status is not None:
            statement = statement.where(AlertModel.status == status)
        try:
            rows = self._session.scalars(statement).all()
        except SQLAlchemyError as exc:
            raise PersistenceError("failed to list alerts") from exc
        return [_to_record(row) for row in rows]

    def _get_or_raise(self, alert_id: int, error_message: str) -> AlertModel:
        try:
            row = self._session.get(AlertModel, alert_id)
        except SQLAlchemyError as exc:
            raise PersistenceError(
                error_message, context={"alert_id": alert_id}
            ) from exc
        if row is None:
            raise PersistenceError(
                f"{error_message}: alert not found", context={"alert_id": alert_id}
            )
        return row

    def _commit_and_return(
        self, row: AlertModel, alert_id: int, error_message: str
    ) -> AlertRecord:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                error_message, context={"alert_id": alert_id}
            ) from exc
        return _to_record(row)


def _to_record(row: AlertModel) -> AlertRecord:
    return AlertRecord(
        id=row.id,
        node_id=row.node_id,
        rule_key=row.rule_key,
        rule_kind=row.rule_kind,
        severity=row.severity,
        status=row.status,
        description=row.description,
        triggering_value=row.triggering_value,
        bound=row.bound,
        first_fired_at=ensure_utc(row.first_fired_at),
        last_fired_at=ensure_utc(row.last_fired_at),
        resolved_at=(
            ensure_utc(row.resolved_at) if row.resolved_at is not None else None
        ),
        acknowledged_at=(
            ensure_utc(row.acknowledged_at) if row.acknowledged_at is not None else None
        ),
        acknowledged_by=row.acknowledged_by,
        escalated_at=(
            ensure_utc(row.escalated_at) if row.escalated_at is not None else None
        ),
    )
