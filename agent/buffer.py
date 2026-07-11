"""Durable local buffering for metrics payloads that could not be delivered.

See ``docs/adr/004-agent-buffering.md`` for the decision this implements.
"""

from pathlib import Path

import structlog

from shared.contracts.v1.metrics import NodeMetricsPayload

logger = structlog.get_logger(__name__)


class FileBuffer:
    """A bounded, JSONL-encoded buffer file for undelivered payloads.

    Rewritten atomically (write-to-temp-file then rename) on every mutating
    operation, to avoid leaving a half-written, corrupt buffer file behind
    if the process is killed mid-write. Bounded by ``max_entries``: once
    full, the oldest buffered entry is evicted to make room for a new one —
    durability here is best-effort, not a substitute for a healthy Collector
    connection.
    """

    def __init__(self, path: str | Path, max_entries: int) -> None:
        self._path = Path(path)
        self._max_entries = max_entries
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def enqueue(self, payload: NodeMetricsPayload) -> None:
        """Append ``payload`` to the buffer, evicting the oldest entry if full."""
        entries = self._read_all()
        entries.append(payload)
        if len(entries) > self._max_entries:
            dropped = len(entries) - self._max_entries
            entries = entries[dropped:]
            logger.warning("buffer_entries_evicted", dropped_count=dropped)
        self._write_all(entries)

    def drain(self, max_items: int) -> list[NodeMetricsPayload]:
        """Remove and return up to ``max_items`` buffered payloads, oldest first."""
        entries = self._read_all()
        to_return, remaining = entries[:max_items], entries[max_items:]
        self._write_all(remaining)
        return to_return

    def __len__(self) -> int:
        return len(self._read_all())

    def _read_all(self) -> list[NodeMetricsPayload]:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.error("buffer_read_failed", path=str(self._path))
            return []

        payloads: list[NodeMetricsPayload] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                payloads.append(NodeMetricsPayload.model_validate_json(line))
            except ValueError:
                logger.error("buffer_entry_corrupt_skipped", path=str(self._path))
        return payloads

    def _write_all(self, entries: list[NodeMetricsPayload]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            serialized = "\n".join(entry.model_dump_json() for entry in entries)
            content = serialized + ("\n" if entries else "")
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(self._path)
        except OSError:
            logger.error("buffer_write_failed", path=str(self._path))
