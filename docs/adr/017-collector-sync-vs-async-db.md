# ADR-017: Collector Sync vs. Async Database Access

## Status

Accepted

_Implemented in `collector/db/session.py` (plain `sqlalchemy.orm.Session`, not
`AsyncSession`), Phase 2._

## Context

ADR-001 chose FastAPI partly for its async support, but async support is a capability,
not an obligation for every code path. Phase 2 needed to decide whether
`collector/repositories/*` use SQLAlchemy's sync `Session` or its `AsyncSession` (backed
by `psycopg`'s async mode), and whether route handlers are `def` or `async def`.

## Decision

Use sync SQLAlchemy (`Session`, `sessionmaker`) throughout the repository layer, and plain
`def` route handlers. FastAPI runs sync `def` handlers in a threadpool automatically, so
this doesn't block the event loop — it just means each request ties up a worker thread for
the duration of its DB calls rather than yielding control during I/O wait.

## Alternatives Considered

- **`AsyncSession` + `async def` routes throughout** — the more "fully async" FastAPI
  idiom, and better suited to high concurrent request volume since it doesn't consume a
  thread per in-flight DB call. Rejected for Phase 2: adds async test fixtures
  (`pytest-asyncio` session-scoped engines), async-aware repository methods, and a second
  mental model (sync Agent code, async Collector code) for no demonstrated throughput
  need yet. `ROADMAP.md` Phase 2 describes a moderate node fleet pushing on a ~30s
  interval — not a workload where thread-per-request is a real bottleneck.
- **Mixed**: async routes with sync DB calls run via `run_in_threadpool` manually —
  strictly worse than letting FastAPI's automatic sync-`def` threadpool handling do the
  same thing implicitly. Rejected as needless complexity.

## Consequences

- Under high concurrent load, the Collector is bounded by its threadpool size (Uvicorn's
  default worker thread count), not just database connection pool size — a real ceiling
  that async access would raise. Not a concern at current expected scale; would need
  revisiting if the Collector's request volume grows substantially (e.g., large fleets,
  sub-second heartbeat intervals).
- Repository code stays simple and directly testable with plain SQLite sessions
  (`tests/unit/collector/conftest.py`'s `db_session` fixture) — no event-loop management
  in tests.
- If async is adopted later, the repository `Protocol`s (`collector/repositories/protocols.py`)
  would need `async def` methods, and every service/route depending on them would change
  in lockstep — a real migration, not a drop-in swap. Worth knowing now so "just make it
  async later" isn't assumed to be free.

## Interview Talking Points

Choosing FastAPI doesn't obligate every code path to be async — the framework's real
async benefit is not blocking the event loop while waiting on I/O, and FastAPI already
gives you that for free with sync `def` handlers via its threadpool. The decision to go
fully async is really a decision about *concurrency ceiling*: async raises the ceiling
(more concurrent in-flight requests than OS threads would allow) at the cost of a more
complex programming model end-to-end. For a Collector serving a moderate Agent fleet on a
30-second push interval, the sync ceiling is nowhere near being tested. The right trigger
to revisit this is a measured one: threadpool saturation or connection-pool exhaustion
under real load, not a preemptive rewrite.
