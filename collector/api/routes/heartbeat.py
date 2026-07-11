"""Heartbeat endpoint — a lighter-weight liveness signal than a full metrics push.

Not called by the Agent in Phase 1/2 (its scheduler cadence is unchanged);
exists so a future phase can add a cheap liveness ping without another
Collector-side change. See ``docs/adr/003-heartbeat-deadman-switch.md``.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from collector.api.deps import get_node_registry_service, verify_api_token
from collector.services.node_registry import NodeRegistryService
from shared.contracts.v1.heartbeat import HeartbeatPing
from shared.contracts.v1.metrics import Ack

router = APIRouter(dependencies=[Depends(verify_api_token)])


@router.post("/api/v1/heartbeat", response_model=Ack)
def receive_heartbeat(
    ping: HeartbeatPing,
    service: NodeRegistryService = Depends(get_node_registry_service),
) -> Ack:
    """Record a liveness signal from an Agent."""
    service.record_seen(ping.node_id, seen_at=ping.sent_at)
    return Ack(accepted=True, received_at=datetime.now(timezone.utc))
