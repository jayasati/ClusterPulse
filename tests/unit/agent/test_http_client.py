"""Unit tests for HttpTransport, using respx to mock the Collector endpoint."""

from datetime import datetime, timezone

import httpx
import pytest
import respx

from agent.transport.http_client import HttpTransport
from shared.contracts.v1.metrics import NodeMetricsPayload
from shared.exceptions import FatalTransportError, RetryableTransportError

BASE_URL = "http://collector.test"
ENDPOINT = f"{BASE_URL}/api/v1/metrics"


def _transport(**overrides) -> HttpTransport:
    defaults = dict(
        base_url=BASE_URL,
        timeout_seconds=1.0,
        retry_attempts=2,
        retry_min_wait_seconds=0.0,
        retry_max_wait_seconds=0.0,
    )
    defaults.update(overrides)
    return HttpTransport(**defaults)


def _payload() -> NodeMetricsPayload:
    return NodeMetricsPayload(node_id="n1", samples=[])


def _ack_json() -> dict:
    return {"accepted": True, "received_at": datetime.now(timezone.utc).isoformat()}


@respx.mock
def test_send_success_returns_ack() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=_ack_json()))
    ack = _transport().send(_payload())
    assert ack.accepted is True


@respx.mock
def test_send_retries_on_server_error_then_succeeds() -> None:
    route = respx.post(ENDPOINT)
    route.side_effect = [httpx.Response(503), httpx.Response(200, json=_ack_json())]

    ack = _transport().send(_payload())

    assert ack.accepted is True
    assert route.call_count == 2


@respx.mock
def test_send_raises_fatal_on_4xx_without_retry() -> None:
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(422))

    with pytest.raises(FatalTransportError):
        _transport().send(_payload())

    assert route.call_count == 1


@respx.mock
def test_send_raises_retryable_after_exhausting_5xx_retries() -> None:
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(500))

    with pytest.raises(RetryableTransportError):
        _transport(retry_attempts=2).send(_payload())

    assert route.call_count == 2


@respx.mock
def test_send_raises_retryable_on_timeout() -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.TimeoutException("boom"))

    with pytest.raises(RetryableTransportError):
        _transport(retry_attempts=1).send(_payload())


@respx.mock
def test_send_raises_retryable_on_connect_error() -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(RetryableTransportError):
        _transport(retry_attempts=1).send(_payload())


def test_close_releases_the_connection_pool() -> None:
    transport = _transport()
    transport.close()  # must not raise
