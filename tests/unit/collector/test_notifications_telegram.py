"""Unit tests for TelegramNotifier, using respx to mock the Bot API."""

import httpx
import respx

from collector.notifications.telegram import TelegramNotifier

BOT_TOKEN = "test-token"
CHAT_ID = "test-chat"
ENDPOINT = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def _notifier() -> TelegramNotifier:
    return TelegramNotifier(BOT_TOKEN, CHAT_ID, timeout_seconds=1.0)


@respx.mock
def test_notify_success_returns_true() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    result = _notifier().notify("hello")

    assert result is True
    assert route.calls.last.request.method == "POST"


@respx.mock
def test_notify_sends_chat_id_and_text() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    _notifier().notify("hello world")

    import json

    body = json.loads(route.calls.last.request.content)
    assert body == {"chat_id": CHAT_ID, "text": "hello world"}


@respx.mock
def test_notify_returns_false_on_4xx_without_raising() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(400, json={"ok": False}))

    result = _notifier().notify("hello")

    assert result is False


@respx.mock
def test_notify_returns_false_on_server_error_without_raising() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(500))

    result = _notifier().notify("hello")

    assert result is False


@respx.mock
def test_notify_returns_false_on_network_error_without_raising() -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("boom"))

    result = _notifier().notify("hello")

    assert result is False


@respx.mock
def test_notify_returns_false_on_timeout_without_raising() -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.TimeoutException("boom"))

    result = _notifier().notify("hello")

    assert result is False


def test_close_releases_the_connection_pool() -> None:
    notifier = _notifier()
    notifier.close()  # must not raise
