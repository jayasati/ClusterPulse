"""End-to-end tests for the alerts read API, exercised through real ingestion
using the Collector's actual shipped ``default_rules.json`` (cpu.usage_percent
> 90 is 'critical') — this also guards the default rule config against
regressions, not just the route wiring.
"""

from datetime import datetime, timedelta, timezone


def _metrics_payload(node_id: str, cpu_value: float, collected_at: datetime) -> dict:
    return {
        "node_id": node_id,
        "collected_at": collected_at.isoformat(),
        "samples": [
            {
                "metric_type": "cpu.usage_percent",
                "value": cpu_value,
                "unit": "percent",
                "labels": {},
            }
        ],
        "collection_errors": [],
    }


def test_list_alerts_requires_auth(collector_client) -> None:
    response = collector_client.get("/api/v1/alerts")
    assert response.status_code == 401


def test_breaching_push_opens_an_alert(collector_client, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    response = collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    assert response.status_code == 200

    alerts = collector_client.get("/api/v1/alerts", headers=auth_headers).json()

    assert len(alerts) == 1
    assert alerts[0]["status"] == "firing"
    assert alerts[0]["rule_key"] == "threshold:cpu.usage_percent"
    assert alerts[0]["node_id"] == "node-1"


def test_non_breaching_push_opens_no_alert(collector_client, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 10.0, now),
        headers=auth_headers,
    )

    alerts = collector_client.get("/api/v1/alerts", headers=auth_headers).json()

    assert alerts == []


def test_repeated_breach_does_not_duplicate_the_alert(
    collector_client, auth_headers
) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    later = now + timedelta(seconds=30)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 96.0, later),
        headers=auth_headers,
    )

    alerts = collector_client.get("/api/v1/alerts", headers=auth_headers).json()

    assert len(alerts) == 1
    assert alerts[0]["triggering_value"] == 96.0


def test_resolving_push_transitions_alert_to_resolved(
    collector_client, auth_headers
) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    later = now + timedelta(seconds=30)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 10.0, later),
        headers=auth_headers,
    )

    alerts = collector_client.get("/api/v1/alerts", headers=auth_headers).json()

    assert len(alerts) == 1
    assert alerts[0]["status"] == "resolved"


def test_list_alerts_filters_by_status(collector_client, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-2", 96.0, now + timedelta(seconds=1)),
        headers=auth_headers,
    )
    later = now + timedelta(seconds=30)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 10.0, later),
        headers=auth_headers,
    )

    firing = collector_client.get(
        "/api/v1/alerts", params={"status": "firing"}, headers=auth_headers
    ).json()
    resolved = collector_client.get(
        "/api/v1/alerts", params={"status": "resolved"}, headers=auth_headers
    ).json()

    assert [a["node_id"] for a in firing] == ["node-2"]
    assert [a["node_id"] for a in resolved] == ["node-1"]


def test_get_alert_returns_the_alert(collector_client, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    alert_id = collector_client.get("/api/v1/alerts", headers=auth_headers).json()[0][
        "id"
    ]

    response = collector_client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == alert_id


def test_get_alert_returns_404_for_unknown_id(collector_client, auth_headers) -> None:
    response = collector_client.get("/api/v1/alerts/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"] == "AlertNotFoundError"


def test_rule_evaluation_failure_does_not_break_ingestion(
    collector_client, auth_headers, monkeypatch
) -> None:
    """A broken Rule Engine must not take down metrics ingestion."""
    from collector.rules import engine as engine_module

    def _broken_evaluate(self, node_id, samples, collected_at):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine_module.RuleEngine, "evaluate", _broken_evaluate)

    response = collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, datetime.now(timezone.utc)),
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def _open_alert_id(collector_client, auth_headers) -> int:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    alerts = collector_client.get("/api/v1/alerts", headers=auth_headers).json()
    return alerts[0]["id"]


def test_acknowledge_requires_auth(collector_client) -> None:
    response = collector_client.post(
        "/api/v1/alerts/1/acknowledge", json={"acknowledged_by": "alice"}
    )
    assert response.status_code == 401


def test_acknowledge_firing_alert_succeeds(collector_client, auth_headers) -> None:
    alert_id = _open_alert_id(collector_client, auth_headers)

    response = collector_client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": "alice"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["acknowledged_by"] == "alice"
    assert body["acknowledged_at"] is not None
    assert body["status"] == "firing"


def test_acknowledge_unknown_alert_returns_404(collector_client, auth_headers) -> None:
    response = collector_client.post(
        "/api/v1/alerts/999999/acknowledge",
        json={"acknowledged_by": "alice"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"] == "AlertNotFoundError"


def test_acknowledge_resolved_alert_returns_409(collector_client, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    later = now + timedelta(seconds=30)
    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 10.0, later),
        headers=auth_headers,
    )
    alert_id = collector_client.get("/api/v1/alerts", headers=auth_headers).json()[0][
        "id"
    ]

    response = collector_client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": "alice"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"] == "AlertAlreadyResolvedError"


def test_acknowledge_missing_body_field_returns_422(
    collector_client, auth_headers
) -> None:
    alert_id = _open_alert_id(collector_client, auth_headers)

    response = collector_client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge", json={}, headers=auth_headers
    )

    assert response.status_code == 422
