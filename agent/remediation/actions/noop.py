"""The NOOP action — exercises the remediation pipeline with zero real effect."""

from shared.contracts.v1.remediation import ActionResult, ActionResultStatus


def execute_noop() -> ActionResult:
    """Do nothing and report success. Used to test dispatch/execution/reporting
    end-to-end without touching the node."""
    return ActionResult(status=ActionResultStatus.EXECUTED, message="noop")
