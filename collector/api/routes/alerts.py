"""Alert read and acknowledgement endpoints."""

from fastapi import APIRouter, Depends

from collector.api.deps import get_alert_evaluation_service, verify_api_token
from collector.api.schemas import AcknowledgeRequest, AlertRead
from collector.enums import AlertStatus
from collector.services.alerting import AlertEvaluationService

router = APIRouter(dependencies=[Depends(verify_api_token)])


@router.get("/api/v1/alerts", response_model=list[AlertRead])
def list_alerts(
    status: AlertStatus | None = None,
    service: AlertEvaluationService = Depends(get_alert_evaluation_service),
) -> list[AlertRead]:
    """List alerts, optionally filtered by ``status`` (``firing``/``resolved``)."""
    return [AlertRead.from_view(view) for view in service.list_alerts(status)]


@router.get("/api/v1/alerts/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: int,
    service: AlertEvaluationService = Depends(get_alert_evaluation_service),
) -> AlertRead:
    """Get a single alert (404 if it doesn't exist)."""
    return AlertRead.from_view(service.get_alert(alert_id))


@router.post("/api/v1/alerts/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(
    alert_id: int,
    body: AcknowledgeRequest,
    service: AlertEvaluationService = Depends(get_alert_evaluation_service),
) -> AlertRead:
    """Acknowledge a firing alert (404 if unknown, 409 if already resolved)."""
    return AlertRead.from_view(service.acknowledge(alert_id, body.acknowledged_by))
