# ADR-003: Heartbeat / Dead-Man Switch

## Status

Accepted

_Implemented in `collector/services/node_registry.py` (`NodeRegistryService`) and
`collector/api/routes/heartbeat.py`, Phase 2._

## Context

The push model (`docs/adr/001-push-vs-pull.md`) means the Collector never initiates
contact with an Agent — it can't poll a node to check liveness. The only signal available
is the *absence* of an expected push. The Collector needs (a) a way to know a node exists
at all, (b) a way to record "this node is still alive," and (c) a way to answer "which
nodes have gone quiet" — without assuming anything about *why* they've gone quiet (Agent
crashed, network partition, node powered off — Phase 2 doesn't need to distinguish these,
only detect "no signal").

## Decision

- **Node Registry, populated lazily.** There is no separate node-provisioning or
  registration step. The first successful authenticated push (metrics or heartbeat) from
  a given `node_id` creates its registry row (`NodeRepository.upsert_seen`). This keeps
  fleet onboarding to "configure the Agent and point it at the Collector" — no manual
  registration workflow to build or operate in Phase 2.
- **A dedicated, lightweight heartbeat endpoint** (`POST /api/v1/heartbeat`), separate
  from `POST /api/v1/metrics`. Both endpoints funnel into the same
  `NodeRegistryService.record_seen()`. The Agent does not call this endpoint yet — Phase
  1's scheduler cadence (one push per collection cycle) is unchanged. The endpoint exists
  now so a future phase can add a cheaper, more frequent liveness ping without a
  Collector-side change.
- **Staleness is a query, computed at read time**, not a background sweep:
  `NodeRegistryService` computes `is_stale = (now - last_seen_at) > stale_after_seconds`
  whenever a node is read (`get_node`/`list_nodes`), where `stale_after_seconds` defaults
  to 90s (`DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS`, three times the Agent's default 30s
  collection interval — three missed cycles before calling a node stale).
- **`last_seen_at` is set from the Collector's own receipt time**, not the Agent-supplied
  `collected_at`/`sent_at` — a skewed Agent clock must not corrupt staleness detection.

## Alternatives Considered

- **Background sweep + push-based alerting** (a scheduled job that periodically scans for
  stale nodes and raises an alert) — this is what a "dead-man switch" conventionally
  implies end-to-end. Rejected for Phase 2 specifically: alerting is Phase 3/4's Rule
  Engine and Alert Manager. Building a scheduler and an alert pathway here would duplicate
  work those phases already own. Phase 2 delivers the *detection primitive*
  (`is_stale`, queryable on demand); Phase 3/4 decides what to do when it's true.
  Deferring this to a purpose-built phase is a deliberate line, not a mistake.
- **Require explicit node registration before accepting pushes** (an admin/provisioning
  endpoint that must be called before a node's data is accepted) — rejected: adds an
  operational step (who calls it, when, with what credentials) not required by
  `ROADMAP.md` Phase 2, and doesn't fit the shared-token auth model (`docs/adr/005-authentication.md`)
  where any valid token is already implicitly "a legitimate Agent."
  Lazy auto-registration is simpler and defers the harder identity question to that ADR.
- **Metrics push doubles as the only liveness signal (no separate heartbeat endpoint)** —
  simpler (one less endpoint), but forces every liveness signal to carry a full metrics
  payload. Rejected: a future phase may want a cheaper, more frequent ping without the
  cost of a full collection cycle; adding the endpoint now avoids a breaking API change
  later, at the cost of one small, currently-unused route in Phase 2.

## Consequences

- Any request bearing a valid shared token can register *any* `node_id` it claims —
  there's no check that the claimed identity is legitimate. This is the direct
  consequence of pairing lazy auto-registration with shared-token auth; see
  `docs/adr/005-authentication.md` for the full tradeoff and mitigation path.
- A node that pushes once and then goes permanently silent stays in the registry forever
  (marked stale, never removed) — there is no expiry/cleanup job in Phase 2. Acceptable at
  current scale; revisit if registry growth becomes a real concern.
- `stale_after_seconds` is a single, Collector-wide default — there's no per-node override
  (e.g., for nodes deliberately configured with a longer collection interval). Noted as a
  future extension, not needed yet since Phase 1 has one fixed default interval.

## Interview Talking Points

This is the same "how do you know a distributed worker is alive when it can't be polled"
problem every push-based monitoring/agent system faces (Datadog Agent, Filebeat, etc.):
you can't distinguish "quiet because it's dead" from "quiet because nothing happened,"
so you settle for "quiet longer than N expected intervals is suspicious enough to flag."
The interesting design choice here isn't the threshold — it's keeping *detection*
(a stateless, query-time computation) strictly separate from *action* (alerting), so the
primitive built in Phase 2 doesn't need to be rebuilt when Phase 3/4 defines what "alert
on this" actually means. Revisit the query-time approach only if list_nodes() polling
frequency from a future Rule Engine becomes expensive at fleet scale — the natural
evolution is a materialized/cached staleness flag, not a fundamentally different
detection mechanism.
