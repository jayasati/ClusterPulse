"""Unit tests for the node registry read endpoints."""

from datetime import datetime, timezone


def _ping(node_id: str) -> dict:
    return {"node_id": node_id, "sent_at": datetime.now(timezone.utc).isoformat()}


def test_list_nodes_empty_when_none_registered(collector_client, auth_headers) -> None:
    response = collector_client.get("/api/v1/nodes", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_nodes_returns_registered_nodes(collector_client, auth_headers) -> None:
    collector_client.post(
        "/api/v1/heartbeat", json=_ping("node-1"), headers=auth_headers
    )
    collector_client.post(
        "/api/v1/heartbeat", json=_ping("node-2"), headers=auth_headers
    )

    response = collector_client.get("/api/v1/nodes", headers=auth_headers)

    node_ids = {node["node_id"] for node in response.json()}
    assert node_ids == {"node-1", "node-2"}


def test_get_node_returns_404_for_unknown_node(collector_client, auth_headers) -> None:
    response = collector_client.get("/api/v1/nodes/never-seen", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"] == "NodeNotFoundError"


def test_get_node_returns_the_node(collector_client, auth_headers) -> None:
    collector_client.post(
        "/api/v1/heartbeat", json=_ping("node-1"), headers=auth_headers
    )

    response = collector_client.get("/api/v1/nodes/node-1", headers=auth_headers)

    body = response.json()
    assert body["node_id"] == "node-1"
    assert body["is_stale"] is False
