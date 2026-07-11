"""Unit tests for POST /api/v1/heartbeat."""

from datetime import datetime, timezone


def _ping(node_id: str = "node-1") -> dict:
    return {"node_id": node_id, "sent_at": datetime.now(timezone.utc).isoformat()}


def test_heartbeat_requires_auth(collector_client) -> None:
    response = collector_client.post("/api/v1/heartbeat", json=_ping())
    assert response.status_code == 401


def test_heartbeat_accepted_and_registers_node(collector_client, auth_headers) -> None:
    response = collector_client.post(
        "/api/v1/heartbeat", json=_ping(), headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True

    node_response = collector_client.get("/api/v1/nodes/node-1", headers=auth_headers)
    assert node_response.status_code == 200
