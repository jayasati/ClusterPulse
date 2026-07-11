# ADR-004: Agent Local Buffering

## Status

Accepted

_Implemented in `agent/buffer.py` (`FileBuffer`), Phase 1._

## Context

The push model (`docs/adr/001-push-vs-pull.md`) means the Agent, not the Collector,
notices when delivery fails. If the Collector is unreachable, restarting, or returning
server errors, the Agent must not silently drop the metrics it already collected — losing
data is exactly the failure mode a monitoring product exists to avoid. At the same time,
the Agent's dependency footprint must stay minimal (`docs/adr/012-python-tech-stack.md`),
ruling out a database as the buffering mechanism.

## Decision

`FileBuffer` persists undelivered `NodeMetricsPayload` instances as a bounded,
JSONL-encoded file:

- **Storage**: one JSON object per line, in `agent_buffer.jsonl` (path configurable).
- **Atomic rewrite**: every mutating operation (`enqueue`, `drain`) writes to a temp file
  and renames it over the real path (`Path.replace`, atomic on POSIX and Windows), so a
  process kill mid-write leaves the previous, valid buffer file intact rather than a
  half-written, corrupt one.
- **Bounded, oldest-first eviction**: once `max_entries` is reached, the oldest buffered
  payload is dropped to make room for a new one; the eviction count is logged.
- **Replay-on-recovery**: `AgentScheduler._drain_buffer` attempts redelivery of buffered
  payloads at the start of every cycle, before collecting fresh data.
- **Best-effort durability**: a read or write failure (disk full, permission denied) is
  logged and treated as "buffer empty" / "write dropped" respectively — it does not crash
  the Agent. Durability here is a mitigation, not a guarantee.

## Alternatives Considered

- **SQLite-backed buffer** — stronger transactional corruption-resistance and query
  capability. Rejected for Phase 1: adds a dependency and schema-migration surface for a
  data structure (an ordered queue, bounded in size) that a flat file already models
  adequately at the expected scale (≤1000 entries by default).
- **In-memory buffer only (no disk persistence)** — simplest possible option, zero I/O.
  Rejected outright: loses all buffered data across an Agent process restart or crash,
  which is precisely the scenario buffering exists to survive.
- **Unbounded buffer growth** — never lose anything, ever. Rejected: an Agent with no
  bound on local disk usage during an extended Collector outage is its own operational
  incident; bounded + oldest-first eviction converts an unbounded-disk-growth failure into
  a bounded, observable data-loss event (logged eviction counts) instead.

## Consequences

- Rewriting the whole file on every operation is O(n) in buffer size per call — acceptable
  at the default bound (1000 entries) but not designed for very large buffer capacities;
  tracked as known technical debt in `.claude/PROJECT.md`.
- A crash between a successful Collector response and the buffer file reflecting that
  (e.g., during `_drain_buffer`'s redelivery loop) is not possible here because `drain()`
  removes an item from the file *before* the caller attempts delivery — but this means a
  crash *after* `drain()` and *before* a successful `send()` loses that item rather than
  re-attempting it. Accepted for Phase 1: the alternative (removing only after confirmed
  delivery) reintroduces the double-send-on-crash question that ADR already accepts
  at-least-once semantics for elsewhere; revisit only if this specific loss mode is
  observed in practice.
- Buffer file format (JSONL of `NodeMetricsPayload`) is coupled to the `shared.contracts.v1`
  wire schema — a `v2` contract bump needs a decision on whether old-format buffered
  entries are migrated, discarded, or read by both versions during rollover.

## Interview Talking Points

The core tension is durability vs. dependency weight, sharpened by the Agent's explicit
minimal-footprint goal. A local file-based journal is a well-known pattern (similar in
spirit to how many logging/metrics agents — e.g., Filebeat's registry file — buffer
locally without a database) for exactly this reason: it gets "survives a restart" for
free from the filesystem, without asking the Agent to run or embed a database. The
bounded-with-eviction policy is a deliberate choice to fail *visibly* (a logged, counted
eviction) rather than *invisibly* (silent unbounded disk growth until the node runs out of
space) or *catastrophically* (an unbounded buffer causing its own outage). Revisit the
SQLite alternative if buffer sizes or corruption-rate in the field ever justify the added
dependency.
