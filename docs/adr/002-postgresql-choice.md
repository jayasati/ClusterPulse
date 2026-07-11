# ADR-002: PostgreSQL over InfluxDB

## Status

Accepted

_Supersedes the informal decision recorded as "ADR-003" in `.claude/DECISIONS.md`._

## Context

The Collector needs to persist node metrics, health status, and heartbeat history
(`.claude/ROADMAP.md` Phase 2 "Database"). This data is inherently time-series-shaped
(timestamped samples per node per metric), which is the classic use case a purpose-built
time-series database (TSDB) is optimized for — but the project also needs strong
relational consistency for node registry, alert lifecycle (Phase 3/4), and remediation
audit logs (Phase 5), and wants to minimize the number of distinct stateful systems it
operates.

## Decision

Use PostgreSQL as the single system of record for all persisted data, including
time-series-shaped metric samples.

## Alternatives Considered

- **InfluxDB (or another purpose-built TSDB)** — better out-of-the-box write throughput and
  downsampling/retention primitives for pure time-series data. Rejected: adds a second
  stateful system to operate, back up, and secure, for data (node registry, alerts,
  remediation audit trail — see ADR-006/007) that isn't time-series-shaped and fits
  PostgreSQL naturally. Operational overhead outweighs the query-performance benefit at
  this project's scale.
- **TimescaleDB (PostgreSQL extension)** — gets TSDB-style chunking/compression while
  staying wire- and tooling-compatible with plain PostgreSQL. Not chosen for the initial
  build (adds an extension dependency before it's proven necessary), but explicitly kept
  as the first escalation path if retention/query performance (ADR-010) becomes a problem
  with vanilla PostgreSQL — migration cost is low precisely because it's still Postgres.
- **SQLite / flat files** — rejected outright: no meaningful concurrent-write story for a
  central Collector receiving pushes from many Agents simultaneously.

## Consequences

- Time-series query patterns (range scans over `(node_id, metric_type, timestamp)`) must
  be supported by deliberate indexing/partitioning in vanilla PostgreSQL rather than
  getting it for free from a TSDB engine — schema design must account for this from the
  first migration.
- Long-term storage growth is a capacity-planning concern earlier than it would be with a
  TSDB's native downsampling — retention/rollup strategy is tracked as its own decision
  (ADR-010), not assumed to be free.
- One operational system (PostgreSQL) to run, back up, and scale, rather than two — directly
  serves the "less operational overhead" goal already recorded in `.claude/DECISIONS.md`.
- SQLAlchemy 2.x + Alembic (ADR-012) is the natural ORM/migration pairing for this choice.

## Interview Talking Points

The tension here is "use the best tool for each data shape" vs. "minimize the number of
stateful systems you operate." A specialized TSDB will out-perform PostgreSQL on raw
time-series ingest/downsampling, but this project's overall data model (registry, alerts,
audit trail, metrics) is mostly relational, and operating two databases means two backup
strategies, two failure modes, two things to monitor. We accepted a known, bounded
performance ceiling on the metrics-ingest path in exchange for one operationally simpler
system — with TimescaleDB identified in advance as the low-cost escalation path if that
ceiling is actually hit, rather than a decision to revisit from scratch.
