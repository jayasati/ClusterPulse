"""Read and result-reporting operations for the Playbook audit log.

Unlike ``AlertEvaluationService``/``NodeRegistryService``, this has no
distinct "View" type — ``RemediationActionRecord`` already carries exactly
what the read API exposes, with no computed field to add on top (contrast
``NodeRegistryService.NodeView``, which adds ``is_stale``).
"""

from datetime import datetime, timezone

from collector.enums import RemediationActionStatus
from collector.exceptions import (
    RemediationActionNotDispatchedError,
    RemediationActionNotFoundError,
)
from collector.repositories.protocols import (
    RemediationActionRecord,
    RemediationActionRepository,
)
from shared.contracts.v1.remediation import ActionResult, ActionResultStatus

_RESULT_STATUS_TO_ACTION_STATUS = {
    ActionResultStatus.EXECUTED: RemediationActionStatus.EXECUTED,
    ActionResultStatus.FAILED: RemediationActionStatus.FAILED,
}


class RemediationActionService:
    """Exposes the Playbook audit log and accepts Agent-reported results."""

    def __init__(self, repository: RemediationActionRepository) -> None:
        self._repository = repository

    def get_action(self, action_id: int) -> RemediationActionRecord:
        """Return the action with ``action_id``, raising if it doesn't exist."""
        record = self._repository.get(action_id)
        if record is None:
            raise RemediationActionNotFoundError(
                f"remediation action {action_id!r} does not exist",
                context={"action_id": action_id},
            )
        return record

    def list_actions(self, node_id: str | None = None) -> list[RemediationActionRecord]:
        """Return every recorded action, optionally filtered to one ``node_id``."""
        return self._repository.list_actions(node_id)

    def report_result(
        self, action_id: int, result: ActionResult
    ) -> RemediationActionRecord:
        """Record the Agent-reported terminal outcome of a dispatched action.

        Raises ``RemediationActionNotDispatchedError`` if the action isn't
        currently ``DISPATCHED`` — a result is only meaningful for an
        action the Collector actually sent out, and only once.
        """
        current = self.get_action(action_id)
        if current.status != RemediationActionStatus.DISPATCHED:
            raise RemediationActionNotDispatchedError(
                f"remediation action {action_id!r} is not awaiting a result "
                f"(status={current.status.value!r})",
                context={"action_id": action_id, "status": current.status.value},
            )
        return self._repository.mark_result(
            action_id,
            status=_RESULT_STATUS_TO_ACTION_STATUS[result.status],
            reason=result.message,
            completed_at=datetime.now(timezone.utc),
        )
