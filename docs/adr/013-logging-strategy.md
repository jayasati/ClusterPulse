# ADR-013: Logging Strategy

## Status

Accepted

## Context

`.claude/CODING_STANDARDS.md` requires "logging instead of `print()`", but ClusterPulse is
a distributed system with potentially many Agent instances plus one central Collector
(ADR-001). Free-text logs are difficult to correlate across that many independent
processes, and the system needs to support future log-based alerting/dashboards without a
log-format rewrite later. Full rationale and design detail:
`docs/architecture/00-project-initialization.md` §6.

## Decision

Use `structlog`, bound to stdlib `logging` (so third-party library log records are
captured uniformly), with:

- Console (human-readable, colored) rendering in `dev`; JSON rendering in `staging`/`prod`.
- A single `configure_logging(settings)` entry point in `shared/logging/setup.py`, called
  once at process startup by both `agent/main.py` and `collector/main.py`.
- Structured key-value fields on every log call (`logger.info("heartbeat_sent", node_id=...)`),
  never string-interpolated messages.
- Correlation identifiers bound via `structlog.contextvars`: a `request_id` per Collector
  HTTP request, a `collection_cycle_id` per Agent scheduler tick.

## Alternatives Considered

- **Stdlib `logging` + a custom/`python-json-logger` formatter** — smaller dependency
  footprint, satisfies the letter of "logging instead of print()" without adding
  `structlog`. Viable, and lighter-weight for the Agent specifically (see ADR-012's
  Agent-footprint concern). Not chosen as the default, but left open — see Open Questions
  below; the JSON-formatter-only route is the fallback if `structlog`'s footprint proves
  unwelcome on the Agent.
- **`loguru`** — pleasant ergonomics out of the box, but weaker interop with stdlib
  `logging` (which third-party libraries use) and a less conventional choice for
  contextvar-based correlation binding. Rejected.
- **No structured logging, plain `logging.info(f"...")` throughout** — fails the
  correlation requirement outright once there's more than one Agent instance; grepping
  free text across a fleet doesn't scale. Rejected.

## Consequences

- Adds one dependency (`structlog`) to both Agent and Collector — a real cost given the
  Agent's minimal-footprint goal (ADR-012); tracked as an explicit open question (design
  doc §12.2) rather than a fully closed decision.
- Every log call site must use structured kwargs, not f-strings — a convention that needs
  to be enforced by review (and potentially a Ruff rule) once code exists to check.
- Logging setup itself must never raise — a misconfigured log level falls back to `INFO`
  with a single warning, so a logging bug can never become a startup-blocking bug.
- Sets up (but does not implement in Phase 0) future ingestion by an external log
  aggregator, since JSON-rendered output in `staging`/`prod` is already aggregator-ready.

## Interview Talking Points

The core trade-off is correlation and machine-parseability (structured logging) vs.
dependency weight and simplicity (plain stdlib logging) — sharper in this project because
the Agent explicitly wants a minimal footprint (ADR-012) while the whole point of
structured logging is strongest exactly where you have many independent Agent processes to
correlate. We chose to pay the dependency cost once, project-wide, for consistency between
Agent and Collector logs, rather than have two different logging approaches per component.
Revisit if Agent footprint measurements (once Phase 1 ships) show `structlog` is a real
problem — the fallback (stdlib `logging` + JSON formatter) preserves the same call-site
API surface (`logger.info(event, **fields)`) closely enough that switching later is a
contained change, not a rewrite.
