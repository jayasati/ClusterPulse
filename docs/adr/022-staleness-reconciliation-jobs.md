# ADR-022: Staleness Alerting and Remediation Reconciliation Jobs

## Status

Accepted (Phase 7)

## Context

Two long-documented gaps shared one root cause — "no Collector-side
scheduler exists" — until ADR-010 built the scheduler:

1. A node that stops pushing entirely is never re-evaluated, so no alert
   can ever fire from silence (the dead-man switch of ADR-003 computed
   `is_stale` but nothing acted on it).
2. A remediation action stuck at `DISPATCHED` (Agent crash or partition
   between dispatch and result-report) stayed an open question forever.

Phase 7's chaos scenarios ("node dies silently", "Agent dies
mid-remediation") need the system to *react* to these, not merely
exhibit them.

## Decision

- **`PeriodicJobScheduler` gains per-job intervals** (`JobSchedule`):
  one daemon thread runs each job on its own cadence, sleeping until the
  soonest due job. Still one thread — overlap-free by construction; a
  slow job delaying another's tick is the accepted cost at this scale.
  The scheduler is built whenever *any* job is enabled.
- **`StalenessJob`** (opt-in, default 60s cadence): opens a `critical`
  alert with the reserved rule_key `staleness:node_heartbeat` for any
  node silent past `heartbeat_stale_after_seconds`, and resolves it when
  the node pushes again — reusing the entire existing alert lifecycle
  (dedup, API, dashboards, Telegram) instead of a parallel mechanism.
  `RuleKind.STALENESS` is added (migration `0006`,
  `ALTER TYPE ... ADD VALUE` in an autocommit block; downgrade is a
  documented no-op since PostgreSQL cannot drop enum values).
  **Startup grace**: the first sweep after process start never opens
  alerts — after a *Collector* outage the whole fleet looks stale at
  once, and alerting on all of it would misattribute our downtime to
  the fleet. Genuinely dead nodes are caught one interval later.
- **`ReconciliationJob`** (opt-in, default 300s cadence): marks
  `DISPATCHED` actions older than `remediation_dispatch_timeout_seconds`
  (default 1800s) as `FAILED` with an explicit timed-out reason. A late
  Agent result still overwrites the timeout verdict — the Agent observed
  the actual execution; the timeout is only the Collector's inference.

## Consequences

- The two biggest tech-debt items close; the audit log now always
  converges to a terminal state, and silent-node death finally pages.
- Staleness alerts do not escalate (escalation remains
  ingestion-triggered, and a silent node ingests nothing) — a staleness
  alert is already `critical` and notifies immediately, so the practical
  loss is small; documented, not solved.
- Staleness flapping mirrors the existing no-flap-damping tradeoff
  (ADR-011): a node oscillating around the 90s boundary churns
  open/resolve. Same future fix (require N consecutive observations).
- One-tick false-negative window: a node dying immediately after a sweep
  is detected up to `interval + stale_after` later — bounded, documented.

## Alternatives considered

- **Escalating staleness alerts from the job**: duplicates escalation
  logic outside `AlertEvaluationService` for marginal benefit over an
  immediate `critical` notification; deferred until escalation itself is
  scheduler-driven.
- **A separate staleness table/notification path**: loses dedup, the
  read API, and dashboards for free; rejected.
- **Deleting timed-out dispatches instead of failing them**: erases the
  only evidence the dispatch happened; the audit log must record the
  timeout, not hide it.
