# ADR-010: Retention Policy — Bounded Pruning via an In-Process Thread Scheduler

## Status

Accepted (Phase 6)

## Context

`metric_samples` grows without bound: one Agent at the default 30-second
interval writes ~26k rows/day, and live verification (see PROJECT.md)
produced 252 rows from a single node in ~20 minutes. Nothing ever deleted
anything. Separately, the Collector had *no* background execution at all —
a gap PROJECT.md's tech-debt list blames for three separate limitations
(staleness alerting, silent-node escalation, stuck-`DISPATCHED`
reconciliation).

## Decision

1. **An in-process, thread-based `PeriodicJobScheduler`**
   (`collector/jobs/scheduler.py`): a daemon thread wakes on an interval
   and runs registered jobs sequentially. Started/stopped by the FastAPI
   lifespan. A thread, not asyncio: the whole persistence stack is
   synchronous SQLAlchemy (`docs/adr/017-collector-sync-vs-async-db.md`), so
   jobs block on I/O — a worker thread is the correct home, and the
   request event loop is exactly the wrong one.

2. **A `RetentionJob`** (`collector/jobs/retention.py`) pruning in
   FK-safe order — terminal `remediation_actions` (90d default), then
   resolved-and-unreferenced `alerts` (30d), then `metric_samples` (7d) —
   in `batch_size`-bounded DELETE transactions
   (`DELETE ... WHERE id IN (SELECT ... LIMIT n)`), each committed
   independently.

3. **Opt-in**: `retention_enabled` defaults to `false`. Turning on data
   deletion must be an operator decision, never an upgrade side effect.

4. **Never pruned, regardless of age**: firing alerts (live state, not
   history), `DISPATCHED` remediation rows (unresolved evidence of an
   Agent that never reported back), and alerts still referenced by any
   audit row (`resolved_alerts_retention_days <=
   remediation_actions_retention_days` is validated at startup, and the
   prune query additionally skips referenced alerts — two independent
   layers, same defense-in-depth pattern as remediation safety, `docs/adr/007-remediation-safety.md`).

## Consequences

- Bounded storage without a new deployment unit; works identically under
  pytest, Docker, and systemd.
- Jobs die with the Collector process — acceptable: retention is not
  time-critical, and the next start resumes exactly where the last batch
  committed (per-batch commits make interruption lossless).
- Single-Collector assumption: no distributed lock. If an HA Collector
  ever ships (Future Features), the scheduler needs leader election or a
  DB advisory lock — documented extension point, not built speculatively.
- The scheduler is deliberately generic (`Job` protocol): staleness
  alerting and `DISPATCHED` reconciliation — both blocked on "no
  scheduler exists" — now have a home to land in.

## Alternatives considered

- **External cron + management command**: externalizes timing, but adds
  an installer surface, splits configuration across two systems, and
  does nothing for the future jobs that need app wiring (notifier,
  repositories) anyway.
- **PostgreSQL partitioning (`pg_partman`) with partition drops**: the
  correct answer at 100× scale (instant drops, no bloat), but heavy
  operational machinery for the current single-digit-node reality.
  Documented as the upgrade path; batched deletes are right-sized now.
- **asyncio background task**: would force `run_in_executor` around every
  repository call or an async DB rewrite, contradicting ADR "sync vs
  async DB" for zero benefit.
