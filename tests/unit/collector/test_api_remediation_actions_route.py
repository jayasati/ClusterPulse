"""End-to-end tests for the remediation-actions API and Ack dispatch, exercised
through real ingestion using the Collector's shipped default rules/playbooks
(``threshold:disk.usage_percent`` maps to a real ``clear_directory`` Playbook).
"""

from datetime import datetime, timedelta, timezone


def _disk_payload(node_id: str, value: float, collected_at: datetime) -> dict:
    return {
        "node_id": node_id,
        "collected_at": collected_at.isoformat(),
        "samples": [
            {
                "metric_type": "disk.usage_percent",
                "value": value,
                "unit": "percent",
                "labels": {},
            }
        ],
        "collection_errors": [],
    }


def test_list_remediation_actions_requires_auth(collector_client) -> None:
    response = collector_client.get("/api/v1/remediation-actions")
    assert response.status_code == 401


def test_no_dispatch_when_remediation_disabled(collector_client, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics", json=_disk_payload("node-1", 90.0, now), headers=auth_headers
    )
    later = now + timedelta(seconds=1)
    ack = collector_client.post(
        "/api/v1/metrics",
        json=_disk_payload("node-1", 91.0, later),
        headers=auth_headers,
    ).json()

    assert ack["pending_actions"] == []
    actions = collector_client.get(
        "/api/v1/remediation-actions", headers=auth_headers
    ).json()
    assert actions == []


def test_second_push_dispatches_and_ack_carries_pending_action(
    collector_client_with_remediation, auth_headers
) -> None:
    now = datetime.now(timezone.utc)
    collector_client_with_remediation.post(
        "/api/v1/metrics", json=_disk_payload("node-1", 90.0, now), headers=auth_headers
    )

    later = now + timedelta(seconds=1)
    response = collector_client_with_remediation.post(
        "/api/v1/metrics",
        json=_disk_payload("node-1", 91.0, later),
        headers=auth_headers,
    )

    ack = response.json()
    assert len(ack["pending_actions"]) == 1
    pending = ack["pending_actions"][0]
    assert pending["action_type"] == "clear_directory"
    assert pending["parameters"]["path"]


def test_dispatched_action_appears_in_audit_log(
    collector_client_with_remediation, auth_headers
) -> None:
    now = datetime.now(timezone.utc)
    collector_client_with_remediation.post(
        "/api/v1/metrics", json=_disk_payload("node-1", 90.0, now), headers=auth_headers
    )
    collector_client_with_remediation.post(
        "/api/v1/metrics",
        json=_disk_payload("node-1", 91.0, now + timedelta(seconds=1)),
        headers=auth_headers,
    )

    actions = collector_client_with_remediation.get(
        "/api/v1/remediation-actions", headers=auth_headers
    ).json()

    assert len(actions) == 1
    assert actions[0]["status"] == "dispatched"
    assert actions[0]["node_id"] == "node-1"
    assert actions[0]["rule_key"] == "threshold:disk.usage_percent"


def test_get_remediation_action_returns_404_for_unknown_id(
    collector_client, auth_headers
) -> None:
    response = collector_client.get(
        "/api/v1/remediation-actions/999999", headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["error"] == "RemediationActionNotFoundError"


def _dispatch_one_action(collector_client_with_remediation, auth_headers) -> int:
    now = datetime.now(timezone.utc)
    collector_client_with_remediation.post(
        "/api/v1/metrics", json=_disk_payload("node-1", 90.0, now), headers=auth_headers
    )
    collector_client_with_remediation.post(
        "/api/v1/metrics",
        json=_disk_payload("node-1", 91.0, now + timedelta(seconds=1)),
        headers=auth_headers,
    )
    actions = collector_client_with_remediation.get(
        "/api/v1/remediation-actions", headers=auth_headers
    ).json()
    return actions[0]["id"]


def test_report_result_requires_auth(collector_client) -> None:
    response = collector_client.post(
        "/api/v1/remediation-actions/1/result", json={"status": "executed"}
    )
    assert response.status_code == 401


def test_report_executed_result_updates_the_action(
    collector_client_with_remediation, auth_headers
) -> None:
    action_id = _dispatch_one_action(collector_client_with_remediation, auth_headers)

    response = collector_client_with_remediation.post(
        f"/api/v1/remediation-actions/{action_id}/result",
        json={"status": "executed", "message": "cleared 3 entries"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "executed"
    assert body["reason"] == "cleared 3 entries"
    assert body["completed_at"] is not None


def test_report_result_for_unknown_action_returns_404(
    collector_client_with_remediation, auth_headers
) -> None:
    response = collector_client_with_remediation.post(
        "/api/v1/remediation-actions/999999/result",
        json={"status": "executed"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_report_result_twice_returns_409(
    collector_client_with_remediation, auth_headers
) -> None:
    action_id = _dispatch_one_action(collector_client_with_remediation, auth_headers)
    collector_client_with_remediation.post(
        f"/api/v1/remediation-actions/{action_id}/result",
        json={"status": "executed"},
        headers=auth_headers,
    )

    response = collector_client_with_remediation.post(
        f"/api/v1/remediation-actions/{action_id}/result",
        json={"status": "executed"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"] == "RemediationActionNotDispatchedError"
