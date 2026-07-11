"""Metrics ingestion endpoint.

Path must stay ``/api/v1/metrics`` — it is hardcoded in
``agent/transport/http_client.py`` and changing it here is a breaking
change to the Agent<->Collector contract.
"""

from fastapi import APIRouter, Depends

from collector.api.deps import get_metrics_ingestion_service, verify_api_token
from collector.services.metrics_ingestion import MetricsIngestionService
from shared.contracts.v1.metrics import Ack, NodeMetricsPayload

router = APIRouter(dependencies=[Depends(verify_api_token)])


@router.post("/api/v1/metrics", response_model=Ack)
def receive_metrics(
    payload: NodeMetricsPayload,
    service: MetricsIngestionService = Depends(get_metrics_ingestion_service),
) -> Ack:
    """Ingest a metrics payload pushed by an Agent."""
    return service.ingest(payload)
