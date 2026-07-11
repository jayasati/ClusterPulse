# Collector — Architecture

Related: `docs/architecture/00-project-initialization.md` (project-wide design),
`docs/adr/002-postgresql-choice.md`, `docs/adr/003-heartbeat-deadman-switch.md`,
`docs/adr/005-authentication.md`, `docs/adr/006-alert-lifecycle.md`,
`docs/adr/016-database-migration-strategy.md`, `docs/adr/017-collector-sync-vs-async-db.md`.

## Overview

The Collector is a FastAPI service layered as: **routes** (HTTP-facing, thin) → **services**
(business logic, framework-agnostic) → **repositories** (SQLAlchemy, the only layer that
knows about the database). Each layer depends only on the abstraction the layer below it
exposes — routes depend on services via FastAPI `Depends`, services depend on repository
`Protocol`s, never on SQLAlchemy or FastAPI directly. This mirrors the Agent's
`AgentScheduler` depending on `shared.protocols`, not concrete classes
(`agent/architecture.md`).

The Rule Engine (`collector/rules/`) is a peer of `repositories/`, not a sub-layer of it —
both are consumed by `services/`. `collector/enums.py` exists specifically so these two
peer packages (`rules/` evaluates, `repositories/` persists) can share the `RuleKind` and
`AlertStatus` vocabulary without either depending on the other.

## Class diagram

```mermaid
classDiagram
    class CollectorSettings {
        +database_url: str
        +api_tokens: str
        +token_set: frozenset~str~
        +heartbeat_stale_after_seconds: float
        +rules_config_path: str
    }

    class NodeRepository { <<Protocol>> }
    class SqlAlchemyNodeRepository
    class MetricsRepository {
        <<Protocol>>
        +bulk_insert(node_id, samples, collected_at, received_at)
        +find_previous_sample(node_id, metric_type, before, window_seconds) MetricSampleRecord
    }
    class SqlAlchemyMetricsRepository
    class AlertRepository {
        <<Protocol>>
        +find_open_alert(node_id, rule_key) AlertRecord
        +create_alert(...) AlertRecord
        +update_last_fired(alert_id, ...) AlertRecord
        +resolve_alert(alert_id, resolved_at) AlertRecord
        +get(alert_id) AlertRecord
        +list_alerts(status) list~AlertRecord~
    }
    class SqlAlchemyAlertRepository

    NodeRepository <|.. SqlAlchemyNodeRepository
    MetricsRepository <|.. SqlAlchemyMetricsRepository
    AlertRepository <|.. SqlAlchemyAlertRepository

    class RulesConfig {
        +threshold_rules: list~ThresholdRuleDefinition~
        +rate_of_change_rules: list~RateOfChangeRuleDefinition~
    }
    class RuleEngine {
        -metrics_repository: MetricsRepository
        +evaluate(node_id, samples, collected_at) list~RuleEvaluationResult~
    }
    RuleEngine --> RulesConfig : configured from
    RuleEngine --> MetricsRepository : depends on (Protocol, rate-of-change lookups only)

    class NodeRegistryService {
        +record_seen(node_id, seen_at) NodeView
        +get_node(node_id) NodeView
        +list_nodes() list~NodeView~
    }
    class AlertEvaluationService {
        -rule_engine: RuleEngine
        -alert_repository: AlertRepository
        +evaluate_and_apply(node_id, samples, collected_at) list~AlertView~
        +get_alert(alert_id) AlertView
        +list_alerts(status) list~AlertView~
    }
    class MetricsIngestionService {
        -metrics_repository: MetricsRepository
        -node_registry: NodeRegistryService
        -alert_evaluation: AlertEvaluationService
        +ingest(payload) Ack
    }

    NodeRegistryService --> NodeRepository : depends on (Protocol)
    AlertEvaluationService --> RuleEngine : depends on (concrete)
    AlertEvaluationService --> AlertRepository : depends on (Protocol)
    MetricsIngestionService --> MetricsRepository : depends on (Protocol)
    MetricsIngestionService --> NodeRegistryService : depends on (concrete)
    MetricsIngestionService --> AlertEvaluationService : depends on (concrete, optional)

    class AlertModel {
        +id: int
        +node_id: str
        +rule_key: str
        +status: AlertStatus
        +first_fired_at: datetime
        +last_fired_at: datetime
        +resolved_at: datetime
    }
    SqlAlchemyAlertRepository --> AlertModel : maps
    AlertModel --> NodeModel : FK node_id
```

`NodeView`/`AlertView` (plain dataclasses returned by services) are distinct from
`NodeRead`/`AlertRead` (the Pydantic models `collector/api/schemas.py` serializes to
JSON) — the service layer never imports Pydantic/FastAPI, and the API layer never
imports SQLAlchemy models directly.

## Sequence diagram — metrics ingestion + rule evaluation

```mermaid
sequenceDiagram
    participant Agent
    participant Route as metrics.receive_metrics
    participant Svc as MetricsIngestionService
    participant NodeRepo as NodeRepository
    participant MetricsRepo as MetricsRepository
    participant AlertSvc as AlertEvaluationService
    participant RuleEng as RuleEngine
    participant AlertRepo as AlertRepository
    participant DB as PostgreSQL

    Agent->>Route: POST /api/v1/metrics (Bearer token, NodeMetricsPayload)
    Route->>Svc: ingest(payload)
    Svc->>NodeRepo: upsert_seen(node_id, collected_at)
    NodeRepo->>DB: INSERT/UPDATE nodes
    Svc->>MetricsRepo: bulk_insert(node_id, samples, ...)
    MetricsRepo->>DB: INSERT metric_samples
    Note over Svc: metrics are now durably persisted
    Svc->>AlertSvc: evaluate_and_apply(node_id, samples, collected_at)
    AlertSvc->>RuleEng: evaluate(node_id, samples, collected_at)
    RuleEng->>MetricsRepo: find_previous_sample(...) [rate-of-change rules only]
    RuleEng-->>AlertSvc: list[RuleEvaluationResult]
    loop each breached/resolved result
        AlertSvc->>AlertRepo: find_open_alert / create_alert / update_last_fired / resolve_alert
    end
    alt rule evaluation raises (any exception)
        AlertSvc-->>Svc: exception
        Note over Svc: logged, swallowed — never propagated
    end
    Svc-->>Route: Ack(accepted=True)
    Route-->>Agent: 200 Ack
```

**Rule evaluation is best-effort by design.** It runs strictly *after* the metrics
transaction succeeds, and any exception from it — `PersistenceError` or a genuine bug
(`AttributeError`, `RuntimeError`, ...) — is caught, logged, and never surfaced as a
failed ingestion. This matters because the Agent's `HttpTransport` treats a non-2xx
response as retryable-or-fatal (`docs/adr/011-http-vs-message-queue.md`); a Rule Engine
bug must never cause the Agent to retry-storm re-delivering metrics that were already
safely persisted.

## Sequence diagram — Alert Lifecycle state machine

```mermaid
sequenceDiagram
    participant AlertSvc as AlertEvaluationService
    participant AlertRepo as AlertRepository

    AlertSvc->>AlertRepo: find_open_alert(node_id, rule_key)
    alt result.breached and no open alert
        AlertRepo-->>AlertSvc: None
        AlertSvc->>AlertRepo: create_alert(...) [status=firing]
    else result.breached and an alert is already open
        AlertRepo-->>AlertSvc: AlertRecord
        AlertSvc->>AlertRepo: update_last_fired(alert_id, value, fired_at)
        Note over AlertSvc: same row — this IS the Phase 3 dedup:<br/>"don't open a duplicate row for an already-firing condition"
    else not result.breached and an alert is open
        AlertRepo-->>AlertSvc: AlertRecord
        AlertSvc->>AlertRepo: resolve_alert(alert_id, resolved_at)
    else not result.breached and no open alert
        AlertRepo-->>AlertSvc: None
        Note over AlertSvc: no-op, nothing to do
    end
```

Two states only: `firing` → `resolved`. No `acknowledged`/`escalated` — those, plus
*notification-level* dedup ("don't re-notify Telegram every minute for the same
still-firing alert," a different concern from the row-level dedup above) and
escalation, are explicitly Phase 4 (`docs/adr/006-alert-lifecycle.md`).

## Why rule evaluation is ingestion-triggered, not scheduled

No background scheduler runs inside the Collector to periodically re-evaluate rules.
Evaluation happens synchronously, inline with `POST /api/v1/metrics`, immediately after
persistence succeeds. This avoids adding a scheduler/async-job dependency
(`docs/adr/017-collector-sync-vs-async-db.md`'s "no complexity without a demonstrated
need" philosophy applies here too) at the cost of never re-evaluating a node that has
gone completely silent — that's a *staleness* alert, a different, still-unimplemented
concern (see Future Extension Notes).

## Why rules are a JSON config file, not a database

`ROADMAP.md` names "Threshold Rules" and "Rate-of-change Rules," not a rule-management
API. A file, loaded once at startup (`collector/rules/loader.py`, stdlib `json`, zero new
dependency), fails Collector startup fast (`ConfigurationError`) on malformed content or
a duplicate rule for the same `(metric_type, kind)`. See `docs/adr/006-alert-lifecycle.md`.

## Why sync SQLAlchemy (not async)

FastAPI runs sync `def` route handlers in a threadpool automatically, so synchronous
repository code doesn't block the event loop. Given the Collector's expected request
volume (occasional pushes from a moderate node fleet, not high-frequency trading), the
complexity of `AsyncSession` (async repository methods, async test fixtures) wasn't
justified yet. See `docs/adr/017-collector-sync-vs-async-db.md`.

## Why Alembic, not `create_all()`

`Base.metadata.create_all()` has no history, no rollback path, and no story for applying
incremental schema changes to a running production database. Both migrations
(`0001_initial_schema.py`, `0002_alerts_table.py`) are hand-written, not autogenerated,
verified via generated offline SQL (`alembic upgrade head --sql`) rather than a live
database — see `docs/adr/016-database-migration-strategy.md`.

## Known limitation: shared-token auth doesn't bind identity

Any request bearing a valid token authenticates as "a legitimate Agent" — there is no
binding between a specific token and a specific `node_id`. A compromised or misconfigured
Agent could push data claiming another node's identity. This is a deliberate, documented
tradeoff (`docs/adr/005-authentication.md`), not an oversight — per-node credentials is
the natural next step once TLS/RBAC (`.claude/PROJECT.md` Future Features) are tackled.

## Known limitation: no flap-damping

A metric oscillating around a threshold across consecutive pushes opens and resolves the
same alert repeatedly ("churn") rather than requiring N consecutive breaches before
firing. Simplest correct behavior for "Alert Lifecycle" as literally named in
`ROADMAP.md` Phase 3; revisit if this becomes a real operational nuisance
(`docs/adr/006-alert-lifecycle.md`).

## Future Extension Notes

- **Per-node credentials**: replace the shared-token model once TLS/RBAC land, closing
  the identity-spoofing gap above.
- **Async DB access**: revisit if profiling shows threadpool contention under real load.
- **Alerting on staleness**: still not implemented. `NodeRegistryService.list_nodes()`
  exposes `is_stale` today, but nothing polls it — that requires a scheduler, which this
  phase deliberately did not add. A future phase adding *any* Collector-side background
  job should reconsider this at the same time.
- **Dynamic rule management**: a database-backed rule CRUD API (with hot-reload) is the
  natural successor to the static JSON config, if per-fleet/per-tenant customization
  becomes a real need.
- **Flap damping**: e.g. requiring N consecutive breaching evaluations before opening an
  alert, to reduce churn on noisy metrics.
- **Label-scoped rules**: rules currently apply per `metric_type` globally, not per label
  (e.g., a disk rule can't target one mount point specifically) — matches the Agent's
  current single-mount-point `DiskCollector`, so not a real functionality gap yet.
- **Telegram delivery, acknowledgement, escalation, notification-level dedup**: Phase 4,
  building on the `firing`/`resolved` alerts this phase produces.
- **Rate limiting**: not implemented; noted as a gap if the Collector is ever exposed
  beyond a trusted network.
