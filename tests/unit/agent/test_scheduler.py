"""Unit tests for AgentScheduler cycle orchestration."""

from datetime import datetime, timezone

from agent.scheduler import AgentScheduler
from shared.constants import MetricType
from shared.contracts.v1.metrics import Ack, MetricSample, NodeMetricsPayload
from shared.contracts.v1.remediation import (
    ActionResult,
    ActionResultStatus,
    PendingAction,
    PlaybookActionType,
)
from shared.exceptions import (
    FatalTransportError,
    RetryableTransportError,
    TransportError,
)


class _FakeCollector:
    def __init__(self, samples=None, error=None) -> None:
        self._samples = samples or []
        self._error = error

    def collect(self):
        if self._error:
            raise self._error
        return self._samples


class _RecordingTransport:
    """A fake Transport whose ``send`` succeeds, or raises the next queued outcome."""

    def __init__(self, outcomes=None, ack=None) -> None:
        self._outcomes = list(outcomes or [])
        self._ack = ack
        self.sent_payloads: list[NodeMetricsPayload] = []
        self.reported_results: list[tuple[int, ActionResult]] = []

    def send(self, payload: NodeMetricsPayload) -> Ack:
        self.sent_payloads.append(payload)
        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
        if self._ack is not None:
            return self._ack
        return Ack(accepted=True, received_at=datetime.now(timezone.utc))

    def report_action_result(self, action_id: int, result: ActionResult) -> None:
        self.reported_results.append((action_id, result))


class _InMemoryBuffer:
    def __init__(self) -> None:
        self._items: list[NodeMetricsPayload] = []

    def enqueue(self, payload: NodeMetricsPayload) -> None:
        self._items.append(payload)

    def drain(self, max_items: int) -> list[NodeMetricsPayload]:
        drained, self._items = self._items[:max_items], self._items[max_items:]
        return drained

    def __len__(self) -> int:
        return len(self._items)


def _sample() -> MetricSample:
    return MetricSample(
        metric_type=MetricType.CPU_USAGE_PERCENT, value=1.0, unit="percent"
    )


def _scheduler(
    collectors=None, transport=None, buffer=None, executor=None
) -> AgentScheduler:
    return AgentScheduler(
        node_id="n1",
        collectors=collectors if collectors is not None else [],
        transport=transport if transport is not None else _RecordingTransport(),
        buffer=buffer if buffer is not None else _InMemoryBuffer(),
        interval_seconds=1.0,
        executor=executor,
    )


def test_run_once_sends_collected_samples() -> None:
    transport = _RecordingTransport()
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])], transport=transport
    )

    scheduler.run_once()

    assert len(transport.sent_payloads) == 1
    assert transport.sent_payloads[0].samples == [_sample()]


def test_one_failing_collector_does_not_block_others() -> None:
    transport = _RecordingTransport()
    scheduler = _scheduler(
        collectors=[
            _FakeCollector(error=RuntimeError("psutil exploded")),
            _FakeCollector(samples=[_sample()]),
        ],
        transport=transport,
    )

    scheduler.run_once()

    sent = transport.sent_payloads[0]
    assert sent.samples == [_sample()]
    assert len(sent.collection_errors) == 1


def test_retryable_delivery_failure_buffers_payload() -> None:
    transport = _RecordingTransport(outcomes=[RetryableTransportError("down")])
    buffer = _InMemoryBuffer()
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        buffer=buffer,
    )

    scheduler.run_once()

    assert len(buffer) == 1


def test_fatal_delivery_failure_is_dropped_not_buffered() -> None:
    transport = _RecordingTransport(outcomes=[FatalTransportError("bad payload")])
    buffer = _InMemoryBuffer()
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        buffer=buffer,
    )

    scheduler.run_once()

    assert len(buffer) == 0


def test_run_once_drains_buffer_before_new_collection() -> None:
    transport = _RecordingTransport()
    buffer = _InMemoryBuffer()
    buffer.enqueue(NodeMetricsPayload(node_id="n1", samples=[]))
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        buffer=buffer,
    )

    scheduler.run_once()

    assert len(transport.sent_payloads) == 2
    assert len(buffer) == 0


def test_drain_failure_requeues_unattempted_items_too() -> None:
    transport = _RecordingTransport(outcomes=[RetryableTransportError("still down")])
    buffer = _InMemoryBuffer()
    buffer.enqueue(NodeMetricsPayload(node_id="n1", samples=[]))
    buffer.enqueue(NodeMetricsPayload(node_id="n1", samples=[]))
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[])], transport=transport, buffer=buffer
    )

    scheduler.run_once()

    # The first buffered item fails and is re-enqueued; the second, never
    # attempted this cycle, must be re-enqueued too rather than silently lost.
    assert len(buffer) == 2


def test_drain_fatal_item_is_dropped_and_remaining_items_still_attempted() -> None:
    transport = _RecordingTransport(outcomes=[FatalTransportError("bad payload")])
    buffer = _InMemoryBuffer()
    buffer.enqueue(NodeMetricsPayload(node_id="n1", samples=[]))
    buffer.enqueue(NodeMetricsPayload(node_id="n1", samples=[]))
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[])], transport=transport, buffer=buffer
    )

    scheduler.run_once()

    # The first buffered item is fatally rejected and dropped (not re-enqueued);
    # the second is still attempted this cycle (no break on a fatal error).
    assert len(buffer) == 0


def test_run_forever_stops_when_flag_set(monkeypatch) -> None:
    sleep_calls = {"count": 0}
    monkeypatch.setattr(
        "agent.scheduler.time.sleep",
        lambda seconds: sleep_calls.__setitem__("count", sleep_calls["count"] + 1),
    )
    scheduler = _scheduler()
    remaining = {"n": 2}

    def should_stop() -> bool:
        remaining["n"] -= 1
        return remaining["n"] < 0

    scheduler.run_forever(should_stop)

    assert sleep_calls["count"] == 2


# --- Remediation: executing pending actions from the Ack -------------------


class _FakeExecutor:
    def __init__(self, result=None) -> None:
        self._result = result or ActionResult(status=ActionResultStatus.EXECUTED)
        self.executed: list[PendingAction] = []

    def execute(self, action: PendingAction) -> ActionResult:
        self.executed.append(action)
        return self._result


def _pending_action(action_id: int = 1) -> PendingAction:
    return PendingAction(
        action_id=action_id,
        action_type=PlaybookActionType.NOOP,
        parameters={},
    )


def test_pending_actions_are_executed_and_results_reported() -> None:
    ack = Ack(
        accepted=True,
        received_at=datetime.now(timezone.utc),
        pending_actions=[_pending_action(1)],
    )
    transport = _RecordingTransport(ack=ack)
    executor = _FakeExecutor(result=ActionResult(status=ActionResultStatus.EXECUTED))
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        executor=executor,
    )

    scheduler.run_once()

    assert len(executor.executed) == 1
    assert executor.executed[0].action_id == 1
    assert transport.reported_results == [
        (1, ActionResult(status=ActionResultStatus.EXECUTED))
    ]


def test_no_executor_means_pending_actions_are_ignored() -> None:
    ack = Ack(
        accepted=True,
        received_at=datetime.now(timezone.utc),
        pending_actions=[_pending_action(1)],
    )
    transport = _RecordingTransport(ack=ack)
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        executor=None,
    )

    scheduler.run_once()  # must not raise despite no executor configured

    assert transport.reported_results == []


def test_multiple_pending_actions_are_all_executed_independently() -> None:
    ack = Ack(
        accepted=True,
        received_at=datetime.now(timezone.utc),
        pending_actions=[_pending_action(1), _pending_action(2)],
    )
    transport = _RecordingTransport(ack=ack)
    executor = _FakeExecutor()
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        executor=executor,
    )

    scheduler.run_once()

    assert len(executor.executed) == 2
    assert {r[0] for r in transport.reported_results} == {1, 2}


def test_result_report_failure_is_logged_and_does_not_raise(monkeypatch) -> None:
    ack = Ack(
        accepted=True,
        received_at=datetime.now(timezone.utc),
        pending_actions=[_pending_action(1)],
    )
    transport = _RecordingTransport(ack=ack)
    monkeypatch.setattr(
        transport,
        "report_action_result",
        lambda *a, **k: (_ for _ in ()).throw(TransportError("network blip")),
    )
    executor = _FakeExecutor()
    scheduler = _scheduler(
        collectors=[_FakeCollector(samples=[_sample()])],
        transport=transport,
        executor=executor,
    )

    scheduler.run_once()  # must not raise
