# Chaos Engineering — Scenarios and Live Results

Chaos scenarios for ClusterPulse, each run against a real two-node AWS
deployment (Ubuntu 24.04 t3.micro pair, ap-south-1; Collector + PostgreSQL 16
on one node, Agent on the other, Collector port reachable only from the
Agent's security group). Results below are from the live run of 2026-07-12.

Configuration under test: `staleness_alerting_enabled=true` (30s sweeps,
90s stale threshold), `remediation_reconciliation_enabled=true` (60s sweeps,
180s dispatch timeout), `retention_enabled=true`.

## Scenario 1 — Silent node death (Agent SIGKILL)

**Hypothesis**: a node whose Agent dies without warning is detected within
`stale_after + sweep_interval`; a critical alert opens, Telegram fires, and
recovery auto-resolves it.

**Injection**: `kill -9` the Agent process.

| Event | Time (UTC) |
|---|---|
| Agent SIGKILLed | 09:53:23 |
| Staleness alert opened (critical, 93s silence vs 90s bound) + Telegram | 09:54:41 |
| Agent restarted | 09:56:00 |
| Alert auto-resolved + Telegram | 09:56:12 |

**Result: PASS.** Detection on the first eligible sweep; exactly one alert
despite repeated sweeps (lifecycle dedup); resolution 12s after recovery.

## Scenario 2 — Remediation dispatch never answered

**Hypothesis**: a `DISPATCHED` remediation action whose Agent never reports
back is marked `FAILED` (timed out) by the reconciliation job.

**Injection**: state injection — a `DISPATCHED` audit row aged past the
timeout (the real Agent-crash-between-Ack-and-result race is sub-second and
not reliably injectable from outside; unit tests cover the boundary cases,
this run verifies the live wiring).

**Result: PASS.** Row flipped to `failed` with reason
`"dispatch timed out — Agent never reported a result …"` on the first sweep.
A late Agent result overwriting the timeout verdict is covered by unit test
(ground truth beats inference).

## Scenario 3 — Network partition (security-group revocation)

**Hypothesis**: an L3 partition (black-holed packets, no RST) causes the
Agent to buffer with `request timed out` classified as retryable, the
Collector to open a staleness alert, and healing to recover everything with
zero data loss.

**Injection**: revoke the Agent-SG → Collector:8000 ingress rule; heal by
restoring it. Pre-partition sample count: 8,577.

| Event | Time (UTC) |
|---|---|
| Partition injected | 10:00:30 |
| Agent buffering (`collector request timed out` → retryable) | 10:01:16 |
| Staleness alert opened + Telegram | 10:02:12 |
| Partition healed | 10:03:15 |
| Alert auto-resolved + Telegram | 10:03:43 |

**Result: PASS.** Buffer drained to 0; samples 8,577 → 8,658 — the partition
window arrived by redelivery, not loss. Notably this exercises the *timeout*
branch of the retry classifier where Scenario 4 exercises the *5xx* branch
and the Phase 5 verification exercised *connection refused* — all three
retryable paths are now proven live.

## Scenario 4 — Database outage (Collector's own dependency)

**Hypothesis**: with PostgreSQL down, the Collector process survives, returns
503 (not a crash) to pushes, contains the background jobs' failures, and
recovers completely when the database returns.

**Injection**: `systemctl stop postgresql` on the Collector host for ~2
minutes.

**Observed**: Collector process alive throughout; Agent received
`503 Service Unavailable`, classified it retryable, buffered 5 payloads;
4 `job_run_failed` log lines — every staleness/reconciliation tick against
the dead DB was contained and the scheduler thread never died. After
`systemctl start postgresql`: pushes back to 200, buffer drained to 0, jobs
back to `job_run_completed`, outage window backfilled.

**Result: PASS.**

## Known-gap scenarios (deliberately not run)

- **Both Collector *and* Agent down simultaneously**: metrics collected by
  nobody are gone — the Agent cannot buffer what it never sampled. Inherent
  to any agent-based design; documented since Phase 1.
- **Disk-full on the Collector host**: PostgreSQL handles ENOSPC by
  refusing writes (degrades to Scenario 4's shape); running it risks
  corrupting the long-lived verification instance for little new signal.
  Candidate for a disposable-instance run.

## Reproduction notes

- Kill processes with a bracketed pattern (`pkill -f "agent[.]main"`) and
  never in the same SSH command as a restart — `pkill -f` matches the
  command string that carries it.
- The Collector's structlog console output embeds ANSI color codes;
  `grep key=value` silently fails against the raw log — strip with
  `sed "s/\x1b\[[0-9;]*m//g"` first.
