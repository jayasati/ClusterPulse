"""End-to-end tests for Telegram notification delivery, triggered through real
metrics ingestion against the Collector's shipped ``default_rules.json``.
"""

from datetime import datetime, timedelta, timezone

import httpx
import respx

from tests.unit.collector.conftest import TELEGRAM_BOT_TOKEN

TELEGRAM_ENDPOINT = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


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


@respx.mock
def test_breaching_push_sends_a_telegram_notification(
    collector_client_with_telegram, auth_headers
) -> None:
    route = respx.post(TELEGRAM_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    response = collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, datetime.now(timezone.utc)),
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert route.call_count == 1


@respx.mock
def test_repeated_breach_does_not_send_a_second_notification(
    collector_client_with_telegram, auth_headers
) -> None:
    route = respx.post(TELEGRAM_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    now = datetime.now(timezone.utc)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )

    later = now + timedelta(seconds=30)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 96.0, later),
        headers=auth_headers,
    )

    assert route.call_count == 1


@respx.mock
def test_resolving_push_sends_a_resolved_notification(
    collector_client_with_telegram, auth_headers
) -> None:
    route = respx.post(TELEGRAM_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    now = datetime.now(timezone.utc)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )

    later = now + timedelta(seconds=30)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 10.0, later),
        headers=auth_headers,
    )

    assert route.call_count == 2
    resolved_body = route.calls[1].request.content.decode()
    assert "RESOLVED" in resolved_body


@respx.mock
def test_telegram_outage_does_not_break_ingestion(
    collector_client_with_telegram, auth_headers
) -> None:
    respx.post(TELEGRAM_ENDPOINT).mock(side_effect=httpx.ConnectError("boom"))

    response = collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, datetime.now(timezone.utc)),
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True


@respx.mock
def test_no_telegram_calls_when_not_configured(collector_client, auth_headers) -> None:
    """``collector_client`` (no Telegram settings) must never call the Bot API."""
    route = respx.post(TELEGRAM_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    collector_client.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, datetime.now(timezone.utc)),
        headers=auth_headers,
    )

    assert route.call_count == 0


@respx.mock
def test_escalation_sends_a_third_notification(
    collector_client_with_telegram, auth_headers
) -> None:
    route = respx.post(TELEGRAM_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    now = datetime.now(timezone.utc)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )

    # Default escalation_after_seconds is 900s; push again well past it.
    later = now + timedelta(seconds=1000)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 96.0, later),
        headers=auth_headers,
    )

    assert route.call_count == 2
    escalated_body = route.calls[1].request.content.decode()
    assert "ESCALATED" in escalated_body


@respx.mock
def test_acknowledged_alert_does_not_escalate(
    collector_client_with_telegram, auth_headers
) -> None:
    route = respx.post(TELEGRAM_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    now = datetime.now(timezone.utc)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 95.0, now),
        headers=auth_headers,
    )
    alert_id = collector_client_with_telegram.get(
        "/api/v1/alerts", headers=auth_headers
    ).json()[0]["id"]
    collector_client_with_telegram.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"acknowledged_by": "alice"},
        headers=auth_headers,
    )

    later = now + timedelta(seconds=1000)
    collector_client_with_telegram.post(
        "/api/v1/metrics",
        json=_metrics_payload("node-1", 96.0, later),
        headers=auth_headers,
    )

    assert route.call_count == 1  # only the original "opened" notification
