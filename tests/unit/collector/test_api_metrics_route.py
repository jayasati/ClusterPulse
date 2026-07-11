"""Unit tests for POST /api/v1/metrics."""

from datetime import datetime, timezone


def _payload() -> dict:
    return {
        "node_id": "node-1",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "samples": [
            {
                "metric_type": "cpu.usage_percent",
                "value": 12.5,
                "unit": "percent",
                "labels": {},
            }
        ],
        "collection_errors": [],
    }


def test_receive_metrics_requires_auth(collector_client) -> None:
    response = collector_client.post("/api/v1/metrics", json=_payload())
    assert response.status_code == 401


def test_receive_metrics_accepts_valid_payload(collector_client, auth_headers) -> None:
    response = collector_client.post(
        "/api/v1/metrics", json=_payload(), headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True


def test_receive_metrics_registers_the_node(collector_client, auth_headers) -> None:
    collector_client.post("/api/v1/metrics", json=_payload(), headers=auth_headers)

    response = collector_client.get("/api/v1/nodes/node-1", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["node_id"] == "node-1"


def test_receive_metrics_rejects_malformed_payload(
    collector_client, auth_headers
) -> None:
    bad_payload = {"node_id": "node-1", "samples": "not-a-list"}

    response = collector_client.post(
        "/api/v1/metrics", json=bad_payload, headers=auth_headers
    )

    assert response.status_code == 422
