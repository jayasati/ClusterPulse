"""Remediation action (Playbook audit log) read and result-reporting endpoints."""

from fastapi import APIRouter, Depends

from collector.api.deps import get_remediation_action_service, verify_api_token
from collector.api.schemas import RemediationActionRead
from collector.services.remediation import RemediationActionService
from shared.contracts.v1.remediation import ActionResult

router = APIRouter(dependencies=[Depends(verify_api_token)])


@router.get("/api/v1/remediation-actions", response_model=list[RemediationActionRead])
def list_remediation_actions(
    node_id: str | None = None,
    service: RemediationActionService = Depends(get_remediation_action_service),
) -> list[RemediationActionRead]:
    """List remediation actions, optionally filtered by ``node_id``."""
    return [
        RemediationActionRead.from_record(record)
        for record in service.list_actions(node_id)
    ]


@router.get(
    "/api/v1/remediation-actions/{action_id}", response_model=RemediationActionRead
)
def get_remediation_action(
    action_id: int,
    service: RemediationActionService = Depends(get_remediation_action_service),
) -> RemediationActionRead:
    """Get a single remediation action (404 if it doesn't exist)."""
    return RemediationActionRead.from_record(service.get_action(action_id))


@router.post(
    "/api/v1/remediation-actions/{action_id}/result",
    response_model=RemediationActionRead,
)
def report_remediation_action_result(
    action_id: int,
    body: ActionResult,
    service: RemediationActionService = Depends(get_remediation_action_service),
) -> RemediationActionRead:
    """Agent-reported terminal outcome of a dispatched action.

    404 if the action doesn't exist; 409 if it isn't currently
    ``DISPATCHED`` (already resolved, or never dispatched to begin with).
    """
    return RemediationActionRead.from_record(service.report_result(action_id, body))
