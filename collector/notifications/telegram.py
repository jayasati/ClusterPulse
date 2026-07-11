"""Telegram Bot API notification delivery."""

import httpx
import structlog

from shared.constants import DEFAULT_HTTP_TIMEOUT_SECONDS, HTTP_CLIENT_ERROR_THRESHOLD

logger = structlog.get_logger(__name__)

_SEND_MESSAGE_PATH = "/sendMessage"


class TelegramNotifier:
    """Delivers alert notifications via the Telegram Bot API.

    Fire-and-forget, single attempt, never raises: any failure (network
    error, non-2xx response) is caught and logged internally. The alert
    record is already durably persisted before this is ever called — a
    Telegram outage must only cost the notice, never the alert state
    itself. See ``docs/adr/018-telegram-notifications.md``.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self._chat_id = chat_id
        self._client = httpx.Client(
            base_url=f"https://api.telegram.org/bot{bot_token}", timeout=timeout_seconds
        )

    def notify(self, message: str) -> bool:
        """Attempt to deliver ``message`` to the configured chat."""
        try:
            response = self._client.post(
                _SEND_MESSAGE_PATH, json={"chat_id": self._chat_id, "text": message}
            )
        except httpx.HTTPError as exc:
            logger.error("telegram_notification_failed", error=str(exc))
            return False
        if response.status_code >= HTTP_CLIENT_ERROR_THRESHOLD:
            logger.error(
                "telegram_notification_rejected", status_code=response.status_code
            )
            return False
        return True

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()
