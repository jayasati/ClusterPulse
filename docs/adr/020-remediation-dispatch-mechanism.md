# ADR-020: Remediation Dispatch Mechanism

## Status

Accepted

_Implemented in `shared/contracts/v1/metrics.py` (`Ack.pending_actions`),
`shared/contracts/v1/remediation.py` (`PendingAction`, `ActionResult`),
`collector/api/routes/remediation_actions.py`, `agent/scheduler.py`, Phase 5._

## Context

Auto-remediation decides on the Collector (which has the alert history and Safety Limit
state) but must execute on the Agent (the only process running on the monitored node).
`docs/adr/001-push-vs-pull.md`/`docs/adr/002-postgresql-choice.md` established Agent-
initiated push specifically so the Collector never needs to reach into an Agent across
NAT/firewalls. Any dispatch mechanism for remediation had to preserve that invariant
rather than reopen it.

## Decision

**No new reverse channel.** Remediation decisions happen synchronously inside the same
`POST /api/v1/metrics` request that already runs rule evaluation, alert transitions, and
escalation (`MetricsIngestionService.ingest` → `AlertEvaluationService.evaluate_and_apply`
→ `RemediationEngine.decide`). Because the decision is made *before* the response is
built, the Collector's `Ack` — the response to a request the Agent itself sent — can carry
any dispatched actions directly: `Ack.pending_actions: list[PendingAction] = []` (default
empty, so this is a backward-compatible wire change; older Agents simply never read the
new field). No polling, no second request needed for dispatch.

**Result reporting is a new endpoint, but still Agent-initiated.** After executing (or
refusing) a `PendingAction`, the Agent calls `POST /api/v1/remediation-actions/{action_id}
/result` itself, immediately, using the same bearer-token auth as every other endpoint.
This is a new endpoint, not a new direction of contact — the Agent is still the one
opening the connection, so ADR-001/002's NAT/firewall rationale is fully preserved.

`AgentScheduler._deliver` is extended: on a successful `send`, it now inspects the
returned `Ack.pending_actions` and, if a `PlaybookExecutor` is configured (Agent's own
`remediation_enabled` opt-in — see `docs/adr/007-remediation-safety.md`), executes each
action and reports its result. A pending action is only acted on for the *current* cycle's
fresh delivery, not for buffered/redelivered payloads from `_drain_buffer` — a stated
scope boundary, not an oversight (see Consequences).

## Alternatives Considered

- **A dedicated polling endpoint** (`GET /api/v1/remediation/pending?node_id=...`) the
  Agent calls on its own schedule, decoupled from the metrics push. Rejected: adds a
  second request per cycle for no benefit — the metrics push already happens on the exact
  cadence needed, and the decision is already known by the time the Ack is built. Purely
  extra latency and complexity for the identical outcome.
- **Reverse dispatch** (Collector calls the Agent directly to hand it an action) — the
  most direct-sounding design, but explicitly rejected: it's precisely the model
  ADR-001/002 ruled out for the exact same NAT/firewall reasons, and nothing about
  remediation changes that reasoning.
- **Piggyback results on the *next* metrics push** instead of a dedicated result endpoint —
  avoids adding a new route. Rejected: couples result-reporting latency to the next
  collection interval (up to `collection_interval_seconds` late) and conflates two
  independent concerns (delivering metrics, reporting an action outcome) in one payload.
  A dedicated, immediately-called endpoint reports results as soon as they're known.

## Consequences

- Remediation dispatch has zero added latency and zero added round trips — it rides the
  request the Agent was already making.
- Buffered/redelivered payloads (from `AgentScheduler._drain_buffer`) never carry
  `pending_actions` execution — their `Ack` responses are received but not inspected for
  pending actions. Stated limitation: a remediation decision made while the Collector
  processes a *stale, buffered* payload could be missed by that specific delivery path.
  Given buffered redelivery is itself a fallback path (the primary path already handles
  the common case), this is an accepted, narrow gap rather than a design flaw.
- No reconciliation loop exists for an action stuck at `DISPATCHED` (Agent crash, dropped
  result-report request) — same root cause as the "no Collector-side scheduler" gap
  already documented for staleness-alerting and escalation.

## Interview Talking Points

The core insight is that "dispatch" doesn't require a new architectural capability at
all — it only looks like it does if you assume the Collector needs to *initiate* contact.
Once the decision is made to *only* ever attempt remediation from data the Collector
already has synchronously during an Agent-initiated request, the entire "how does the
Collector reach the Agent" question dissolves: it just reads the same request's response.
The one genuinely new piece — result reporting — still had to preserve the direction of
contact, and making it Agent-initiated (a fire-once-immediately request, not a piggyback on
the next push) kept it simple without compromising the project's established NAT-
traversal rationale.
