"""Sequential collection-and-delivery scheduling for the Agent."""

import time
from typing import Callable

import structlog

from agent.remediation.executor import PlaybookExecutor
from shared.constants import DEFAULT_BUFFER_DRAIN_BATCH_SIZE
from shared.contracts.v1.metrics import Ack, NodeMetricsPayload
from shared.contracts.v1.remediation import ActionResult
from shared.exceptions import FatalTransportError, TransportError
from shared.protocols import MetricCollector, MetricsBuffer, Transport

logger = structlog.get_logger(__name__)


class AgentScheduler:
    """Runs collection cycles at a fixed interval, sequentially.

    Each cycle: drain any previously buffered payloads (best-effort),
    collect fresh samples, attempt delivery, and buffer on retryable
    failure. Cycles never overlap — a slow cycle simply delays the next
    tick, rather than running concurrently with it.

    Phase 5 adds: executing any ``pending_actions`` the Collector attached
    to this cycle's ``Ack`` and reporting each result back — only for the
    current cycle's fresh delivery, not for buffered/redelivered payloads
    (a documented limitation, not an oversight). ``executor`` is ``None``
    unless this Agent's own ``remediation_enabled`` opt-in is set — the
    second of the two independent opt-ins gating real execution. See
    ``docs/adr/007-remediation-safety.md``.
    """

    def __init__(
        self,
        node_id: str,
        collectors: list[MetricCollector],
        transport: Transport,
        buffer: MetricsBuffer,
        interval_seconds: float,
        executor: PlaybookExecutor | None = None,
    ) -> None:
        self._node_id = node_id
        self._collectors = collectors
        self._transport = transport
        self._buffer = buffer
        self._interval_seconds = interval_seconds
        self._executor = executor

    def run_once(self) -> None:
        """Execute a single collection-and-delivery cycle."""
        self._drain_buffer()
        payload = self._collect()
        self._deliver(payload)

    def run_forever(self, should_stop: Callable[[], bool]) -> None:
        """Run cycles until ``should_stop`` returns ``True``, sleeping between them."""
        while not should_stop():
            self.run_once()
            time.sleep(self._interval_seconds)

    def _drain_buffer(self) -> None:
        """Attempt to redeliver buffered payloads before this cycle's fresh one.

        Anything drained but not yet attempted when a failure stops the
        loop is re-enqueued, so a single failure never silently drops the
        rest of the batch.
        """
        drained = self._buffer.drain(DEFAULT_BUFFER_DRAIN_BATCH_SIZE)
        for index, payload in enumerate(drained):
            try:
                self._transport.send(payload)
            except FatalTransportError as exc:
                logger.error(
                    "buffered_payload_rejected_dropped",
                    node_id=self._node_id,
                    error=str(exc),
                )
            except TransportError as exc:
                logger.warning(
                    "buffered_payload_redelivery_failed",
                    node_id=self._node_id,
                    error=str(exc),
                )
                for remaining in drained[index:]:
                    self._buffer.enqueue(remaining)
                break

    def _collect(self) -> NodeMetricsPayload:
        """Run every collector, isolating one collector's failure from the rest."""
        samples = []
        errors = []
        for collector in self._collectors:
            try:
                samples.extend(collector.collect())
            except (
                Exception
            ) as exc:  # noqa: BLE001 - third-party (psutil) errors are unpredictable
                logger.error(
                    "collector_failed",
                    collector=type(collector).__name__,
                    error=str(exc),
                )
                errors.append(f"{type(collector).__name__}: {exc}")
        return NodeMetricsPayload(
            node_id=self._node_id, samples=samples, collection_errors=errors
        )

    def _deliver(self, payload: NodeMetricsPayload) -> None:
        """Send the current cycle's payload, buffering it on retryable failure."""
        try:
            ack = self._transport.send(payload)
        except FatalTransportError as exc:
            logger.error(
                "payload_rejected_dropped", node_id=self._node_id, error=str(exc)
            )
            return
        except TransportError as exc:
            logger.warning(
                "payload_delivery_failed_buffering",
                node_id=self._node_id,
                error=str(exc),
            )
            self._buffer.enqueue(payload)
            return
        self._execute_pending_actions(ack)

    def _execute_pending_actions(self, ack: Ack) -> None:
        if self._executor is None:
            return
        for action in ack.pending_actions:
            result = self._executor.execute(action)
            self._report_action_result(action.action_id, result)

    def _report_action_result(self, action_id: int, result: ActionResult) -> None:
        try:
            self._transport.report_action_result(action_id, result)
        except TransportError as exc:
            logger.warning(
                "remediation_result_report_failed",
                node_id=self._node_id,
                action_id=action_id,
                error=str(exc),
            )
