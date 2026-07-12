# Stress Test — Fleet-Scale Load Results

Tool: `scripts/stress_load.py` (asyncio + httpx swarm of virtual agents,
`stress-` node prefix, sub-threshold metric values so no alerts fire).
Run of 2026-07-12: generator on one t3.micro in-VPC, target Collector on
another t3.micro that also hosts PostgreSQL 16 and Grafana (911 MB RAM
total — a deliberately harsh, cost-floor configuration). 40s per step,
5s push interval, full 5-sample payloads, rule evaluation on every push.

## Results

| Virtual agents | Requests | OK | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 10 | 80 | 100% | 35 ms | 229 ms | 245 ms |
| 25 | 200 | 99% | 24 ms | 360 ms | 403 ms |
| 50 | 400 | 99.75% | 60 ms | 598 ms | 710 ms |
| 100 | 300 | **0%** | 10.1 s (client timeout) | — | — |
| 200 | 600 | **0%** | 10.2 s | — | — |

**Ceiling: ~50 agents at 5s intervals** (≈10 pushes/s, 50 samples/s) on
this hardware. Between 50 and 100 concurrent agents the service does not
degrade — it collapses: every request exceeds the 10s client timeout.

## The important finding: saturation is not self-healing

After load stopped, the Collector stayed wedged: `/healthz` timing out,
every push failing `failed to record node heartbeat`, CPU idle.
PostgreSQL showed the smoking gun:

```
SELECT count(*), state FROM pg_stat_activity WHERE datname='clusterpulse' GROUP BY state;
 15 | idle in transaction
```

Exactly SQLAlchemy's default pool capacity (pool_size 5 + max_overflow
10), all stuck **idle in transaction** — requests abandoned by
timed-out clients leaked their sessions mid-transaction, exhausting the
pool permanently. Background jobs kept running (they use short-lived
sessions that were already pool-checked-out successfully), which is why
the scheduler stayed healthy while the API was dead. Recovery required a
Collector restart.

Recorded as Known Technical Debt; the fix directions, in order of value:

1. Guarantee session rollback/close on the request-abandoned path
   (dependency teardown must run — or `pool_timeout` + `pool_pre_ping`
   as a backstop so checkouts fail fast instead of queueing forever).
2. Backpressure: return 429/503 quickly when saturated instead of
   queueing until client timeout — Agents already handle 5xx correctly
   (buffer and retry), so shedding load is safe by design.
3. Capacity: a larger instance or separated DB host moves the cliff, but
   items 1–2 are what make the cliff survivable.

## Reproduction

```bash
python scripts/stress_load.py --url http://COLLECTOR:8000 --token TOKEN \
    --steps 10,25,50,100 --duration 40 --interval 5
# afterwards:
#   DELETE FROM metric_samples WHERE node_id LIKE 'stress-%';
#   DELETE FROM nodes WHERE node_id LIKE 'stress-%';
# and disable staleness alerting during the run, or every virtual node
# pages when the swarm stops.
```
