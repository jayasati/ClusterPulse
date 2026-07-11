"""Unit tests for FileBuffer."""

from datetime import datetime, timezone

from agent.buffer import FileBuffer
from shared.contracts.v1.metrics import NodeMetricsPayload


def _payload(node_id: str) -> NodeMetricsPayload:
    return NodeMetricsPayload(
        node_id=node_id, collected_at=datetime.now(timezone.utc), samples=[]
    )


def test_enqueue_and_drain_round_trip(buffer_path) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=10)
    buffer.enqueue(_payload("a"))
    buffer.enqueue(_payload("b"))
    assert len(buffer) == 2

    drained = buffer.drain(max_items=10)
    assert [p.node_id for p in drained] == ["a", "b"]
    assert len(buffer) == 0


def test_drain_respects_max_items_and_preserves_fifo_order(buffer_path) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=10)
    for node_id in ["a", "b", "c"]:
        buffer.enqueue(_payload(node_id))

    first_batch = buffer.drain(max_items=2)
    assert [p.node_id for p in first_batch] == ["a", "b"]
    assert len(buffer) == 1


def test_enqueue_evicts_oldest_when_full(buffer_path) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=2)
    buffer.enqueue(_payload("a"))
    buffer.enqueue(_payload("b"))
    buffer.enqueue(_payload("c"))

    remaining = buffer.drain(max_items=10)
    assert [p.node_id for p in remaining] == ["b", "c"]


def test_buffer_survives_process_restart(buffer_path) -> None:
    FileBuffer(path=buffer_path, max_entries=10).enqueue(_payload("a"))
    reopened = FileBuffer(path=buffer_path, max_entries=10)
    assert len(reopened) == 1


def test_corrupt_line_is_skipped_not_fatal(buffer_path) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=10)
    buffer.enqueue(_payload("a"))
    with open(buffer_path, "a", encoding="utf-8") as f:
        f.write("not-valid-json\n")

    drained = buffer.drain(max_items=10)
    assert [p.node_id for p in drained] == ["a"]


def test_drain_on_empty_buffer_returns_empty_list(buffer_path) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=10)
    assert buffer.drain(max_items=10) == []


def test_read_failure_is_swallowed_and_treated_as_empty(
    buffer_path, monkeypatch
) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=10)
    buffer.enqueue(_payload("a"))

    def _raise_os_error(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(type(buffer_path), "read_text", _raise_os_error)

    assert len(buffer) == 0
    assert buffer.drain(max_items=10) == []


def test_write_failure_does_not_raise(buffer_path, monkeypatch) -> None:
    buffer = FileBuffer(path=buffer_path, max_entries=10)

    def _raise_os_error(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(type(buffer_path), "write_text", _raise_os_error)

    buffer.enqueue(_payload("a"))  # must not raise

    assert len(buffer) == 0
    assert len(buffer) == 0
