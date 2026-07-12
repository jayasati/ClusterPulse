"""The Collector <-> Agent remediation wire contract (v1).

``PlaybookActionType`` is the catalog of action kinds both sides must agree
on: the Collector picks one when a Playbook's condition is met
(``collector/remediation/``), and the Agent's ``PlaybookExecutor`` decides
whether it knows how to (and is allowed to) carry it out
(``agent/remediation/``). Kept in ``shared``, not ``collector.enums`` —
unlike ``RemediationActionStatus`` (the Collector's own audit-log
lifecycle, an internal-only concern), this type is genuinely bilateral.
"""

from enum import Enum

from pydantic import BaseModel, Field


class PlaybookActionType(str, Enum):
    """A remediation action kind. See ``docs/adr/007-remediation-safety.md``.

    ``RESTART_SERVICE`` is reserved but not implemented by any Agent-side
    executor as of Phase 5 — it requires a privileged-execution model
    (root/sudo) that is an explicit future extension.
    """

    NOOP = "noop"
    CLEAR_DIRECTORY = "clear_directory"
    RESTART_SERVICE = "restart_service"


class PendingAction(BaseModel):
    """One Playbook the Collector dispatched, carried on the next ``Ack``."""

    action_id: int
    action_type: PlaybookActionType
    parameters: dict[str, str] = Field(default_factory=dict)


class ActionResultStatus(str, Enum):
    """The terminal outcome the Agent reports back for a dispatched action."""

    EXECUTED = "executed"
    FAILED = "failed"


class ActionResult(BaseModel):
    """The Agent's report of what happened when it ran a ``PendingAction``.

    Posted to ``POST /api/v1/remediation-actions/{action_id}/result`` —
    Agent-initiated, consistent with the push-only architecture
    (``docs/adr/001-push-vs-pull.md``, ``docs/adr/002-postgresql-choice.md``).
    """

    status: ActionResultStatus
    message: str | None = None
