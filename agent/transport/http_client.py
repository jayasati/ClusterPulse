"""HTTP transport for delivering metrics payloads to the Collector.

See ``docs/adr/001-push-vs-pull.md`` (direction) and
``docs/adr/011-http-vs-message-queue.md`` (mechanism) for the decisions this
implements.
"""

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.constants import HTTP_CLIENT_ERROR_THRESHOLD, HTTP_SERVER_ERROR_THRESHOLD
from shared.contracts.v1.metrics import Ack, NodeMetricsPayload
from shared.contracts.v1.remediation import ActionResult
from shared.exceptions import FatalTransportError, RetryableTransportError

logger = structlog.get_logger(__name__)

_METRICS_ENDPOINT = "/api/v1/metrics"
_REMEDIATION_ACTIONS_ENDPOINT = "/api/v1/remediation-actions"


class HttpTransport:
    """Delivers ``NodeMetricsPayload`` instances to the Collector over HTTP.

    Retryable failures (timeouts, connection errors, 5xx) are retried with
    bounded exponential backoff. Non-retryable failures (4xx) raise
    immediately as ``FatalTransportError`` — retrying a rejected payload
    will never succeed, so the caller (``AgentScheduler``) can tell the two
    apart and decide whether to buffer.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        retry_attempts: int,
        retry_min_wait_seconds: float,
        retry_max_wait_seconds: float,
        auth_token: str | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout_seconds, headers=headers
        )
        retry_policy = retry(
            reraise=True,
            stop=stop_after_attempt(retry_attempts),
            wait=wait_exponential(
                min=retry_min_wait_seconds, max=retry_max_wait_seconds
            ),
            retry=retry_if_exception_type(RetryableTransportError),
        )
        self._send_with_retry = retry_policy(self._send_once)
        self._report_result_with_retry = retry_policy(self._report_action_result_once)

    def send(self, payload: NodeMetricsPayload) -> Ack:
        """Send ``payload`` to the Collector, retrying transient failures."""
        return self._send_with_retry(payload)

    def report_action_result(self, action_id: int, result: ActionResult) -> None:
        """Report a dispatched action's outcome, retrying transient failures.

        Best-effort beyond the retry policy: a caller that still sees a
        ``TransportError`` after retries logs it and moves on — there is
        no buffering for action results (unlike metrics payloads)."""
        self._report_result_with_retry(action_id, result)

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def _send_once(self, payload: NodeMetricsPayload) -> Ack:
        """Perform a single HTTP request, classifying failures by type."""
        response = self._post(_METRICS_ENDPOINT, payload.model_dump(mode="json"))
        return Ack.model_validate_json(response.text)

    def _report_action_result_once(self, action_id: int, result: ActionResult) -> None:
        """Perform a single HTTP request reporting one action's result."""
        endpoint = f"{_REMEDIATION_ACTIONS_ENDPOINT}/{action_id}/result"
        self._post(endpoint, result.model_dump(mode="json"))

    def _post(self, endpoint: str, json_body: dict[str, object]) -> httpx.Response:
        """POST ``json_body`` to ``endpoint``, classifying failures by type."""
        try:
            response = self._client.post(endpoint, json=json_body)
        except httpx.TimeoutException as exc:
            raise RetryableTransportError(
                "collector request timed out", context={"endpoint": endpoint}
            ) from exc
        except httpx.ConnectError as exc:
            raise RetryableTransportError(
                "collector connection failed", context={"endpoint": endpoint}
            ) from exc

        if response.status_code >= HTTP_SERVER_ERROR_THRESHOLD:
            raise RetryableTransportError(
                "collector returned a server error",
                context={"status_code": response.status_code},
            )
        if response.status_code >= HTTP_CLIENT_ERROR_THRESHOLD:
            raise FatalTransportError(
                "collector rejected the payload",
                context={"status_code": response.status_code},
            )
        return response
