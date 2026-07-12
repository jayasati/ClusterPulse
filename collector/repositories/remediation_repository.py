"""SQLAlchemy-backed ``RemediationActionRepository`` implementation."""

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from collector.db.models.remediation_action import RemediationActionModel
from collector.db.timeutil import ensure_utc
from collector.enums import RemediationActionStatus
from collector.repositories.protocols import RemediationActionRecord
from shared.contracts.v1.remediation import PlaybookActionType
from shared.exceptions import PersistenceError


class SqlAlchemyRemediationActionRepository:
    """Persists remediation decisions (the Playbook audit log) via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_action(
        self,
        node_id: str,
        alert_id: int,
        rule_key: str,
        playbook_name: str,
        action_type: PlaybookActionType,
        parameters: dict[str, str],
        status: RemediationActionStatus,
        reason: str | None,
        created_at: datetime,
    ) -> RemediationActionRecord:
        """Record a new remediation decision (dispatched or safety-blocked)."""
        row = RemediationActionModel(
            node_id=node_id,
            alert_id=alert_id,
            rule_key=rule_key,
            playbook_name=playbook_name,
            action_type=action_type,
            parameters=parameters,
            status=status,
            reason=reason,
            created_at=created_at,
            completed_at=None,
        )
        try:
            self._session.add(row)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                "failed to create remediation action",
                context={"node_id": node_id, "playbook_name": playbook_name},
            ) from exc
        return _to_record(row)

    def mark_result(
        self,
        action_id: int,
        status: RemediationActionStatus,
        reason: str | None,
        completed_at: datetime,
    ) -> RemediationActionRecord:
        """Record the Agent-reported terminal outcome of a dispatched action."""
        row = self._get_or_raise(action_id, "failed to mark remediation action result")
        row.status = status
        row.reason = reason
        row.completed_at = completed_at
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                "failed to mark remediation action result",
                context={"action_id": action_id},
            ) from exc
        return _to_record(row)

    def count_recent_actions(self, node_id: str, since: datetime) -> int:
        """Count actions created for ``node_id`` at or after ``since`` (any status)."""
        statement = (
            select(func.count())
            .select_from(RemediationActionModel)
            .where(
                RemediationActionModel.node_id == node_id,
                RemediationActionModel.created_at >= since,
            )
        )
        try:
            return self._session.scalar(statement) or 0
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to count recent remediation actions",
                context={"node_id": node_id},
            ) from exc

    def find_last_action(
        self, node_id: str, playbook_name: str
    ) -> RemediationActionRecord | None:
        """Return the most recently created action for ``(node_id, playbook_name)``."""
        statement = (
            select(RemediationActionModel)
            .where(
                RemediationActionModel.node_id == node_id,
                RemediationActionModel.playbook_name == playbook_name,
            )
            .order_by(RemediationActionModel.created_at.desc())
            .limit(1)
        )
        try:
            row = self._session.scalars(statement).first()
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to look up last remediation action",
                context={"node_id": node_id, "playbook_name": playbook_name},
            ) from exc
        return _to_record(row) if row is not None else None

    def get(self, action_id: int) -> RemediationActionRecord | None:
        """Return the action with ``action_id``, or ``None`` if unknown."""
        try:
            row = self._session.get(RemediationActionModel, action_id)
        except SQLAlchemyError as exc:
            raise PersistenceError(
                "failed to fetch remediation action",
                context={"action_id": action_id},
            ) from exc
        return _to_record(row) if row is not None else None

    def list_actions(self, node_id: str | None = None) -> list[RemediationActionRecord]:
        """Return every recorded action, optionally filtered to one ``node_id``."""
        statement = select(RemediationActionModel)
        if node_id is not None:
            statement = statement.where(RemediationActionModel.node_id == node_id)
        try:
            rows = self._session.scalars(statement).all()
        except SQLAlchemyError as exc:
            raise PersistenceError("failed to list remediation actions") from exc
        return [_to_record(row) for row in rows]

    def prune_terminal_before(self, cutoff: datetime, batch_size: int) -> int:
        """Delete up to ``batch_size`` terminal actions created before ``cutoff``.

        ``DISPATCHED`` rows are excluded regardless of age — an action the
        Agent never reported back on is unresolved evidence (crash or
        partition between dispatch and result-report), and the audit log
        is the only place that records it.
        """
        doomed = (
            select(RemediationActionModel.id)
            .where(
                RemediationActionModel.status != RemediationActionStatus.DISPATCHED,
                RemediationActionModel.created_at < cutoff,
            )
            .limit(batch_size)
        )
        statement = delete(RemediationActionModel).where(
            RemediationActionModel.id.in_(doomed)
        )
        try:
            result = cast(CursorResult[Any], self._session.execute(statement))
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(
                "failed to prune remediation actions",
                context={"cutoff": cutoff.isoformat()},
            ) from exc
        return int(result.rowcount)

    def _get_or_raise(
        self, action_id: int, error_message: str
    ) -> RemediationActionModel:
        try:
            row = self._session.get(RemediationActionModel, action_id)
        except SQLAlchemyError as exc:
            raise PersistenceError(
                error_message, context={"action_id": action_id}
            ) from exc
        if row is None:
            raise PersistenceError(
                f"{error_message}: action not found",
                context={"action_id": action_id},
            )
        return row


def _to_record(row: RemediationActionModel) -> RemediationActionRecord:
    return RemediationActionRecord(
        id=row.id,
        node_id=row.node_id,
        alert_id=row.alert_id,
        rule_key=row.rule_key,
        playbook_name=row.playbook_name,
        action_type=row.action_type,
        parameters=row.parameters,
        status=row.status,
        reason=row.reason,
        created_at=ensure_utc(row.created_at),
        completed_at=(
            ensure_utc(row.completed_at) if row.completed_at is not None else None
        ),
    )
