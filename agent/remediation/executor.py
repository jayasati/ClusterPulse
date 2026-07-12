"""PlaybookExecutor: carries out (or safely refuses) one dispatched action."""

import structlog

from agent.remediation.actions.clear_directory import execute_clear_directory
from agent.remediation.actions.noop import execute_noop
from shared.contracts.v1.remediation import (
    ActionResult,
    ActionResultStatus,
    PendingAction,
    PlaybookActionType,
)
from shared.exceptions import RemediationSafetyError

logger = structlog.get_logger(__name__)


class PlaybookExecutor:
    """Executes a small, fixed catalog of safe, unprivileged remediation actions.

    ``RESTART_SERVICE`` (and anything else not in the catalog below) is
    refused, not attempted — it requires a privileged-execution model this
    Agent does not implement. See ``docs/adr/007-remediation-safety.md``.
    """

    def __init__(self, allowed_directories: frozenset[str]) -> None:
        self._allowed_directories = allowed_directories

    def execute(self, action: PendingAction) -> ActionResult:
        """Run ``action``, never raising — failures become a ``FAILED`` result."""
        try:
            return self._dispatch(action)
        except (RemediationSafetyError, OSError) as exc:
            logger.warning(
                "remediation_action_failed",
                action_id=action.action_id,
                action_type=action.action_type.value,
                error=str(exc),
            )
            return ActionResult(status=ActionResultStatus.FAILED, message=str(exc))

    def _dispatch(self, action: PendingAction) -> ActionResult:
        if action.action_type == PlaybookActionType.NOOP:
            return execute_noop()
        if action.action_type == PlaybookActionType.CLEAR_DIRECTORY:
            return execute_clear_directory(action.parameters, self._allowed_directories)
        raise RemediationSafetyError(
            f"action_type {action.action_type.value!r} is not supported by this "
            "Agent's executor",
            context={"action_type": action.action_type.value},
        )
