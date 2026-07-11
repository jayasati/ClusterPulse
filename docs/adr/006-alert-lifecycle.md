# ADR-006: Alert Lifecycle

## Status

Accepted

_Implemented in `collector/rules/` (Rule Engine), `collector/services/alerting.py`
(`AlertEvaluationService`), `collector/repositories/alert_repository.py`, and
`collector/db/models/alert.py`, Phase 3._

## Context

`ROADMAP.md` Phase 3 names four things: Rule Engine, Threshold Rules, Rate-of-change
Rules, Alert Lifecycle. Three design questions had to be resolved together, since they
constrain each other: (1) where rule *definitions* come from, (2) when rules are
*evaluated*, and (3) what states an *alert* moves through as a result. Phase 2 explicitly
deferred all three ("kept out of `constants.py` for now to avoid speculative additions
with no consumer" — `shared/architecture.md`) until this phase had a real need for them.

## Decision

**Rule definitions**: a static JSON config file (`collector/rules/default_rules.json` by
default, path configurable via `CollectorSettings.rules_config_path`), loaded once at
Collector startup by `collector/rules/loader.py` (stdlib `json`, no new dependency).
At most one threshold rule and one rate-of-change rule per `metric_type` — enforced by a
Pydantic validator on `RulesConfig`, so a duplicate fails startup with
`ConfigurationError` rather than silently picking one.

**Rule evaluation trigger**: synchronous, inline with `POST /api/v1/metrics` ingestion —
not a background scheduler. `MetricsIngestionService.ingest()` persists the payload first,
then (if an `AlertEvaluationService` collaborator was provided — optional, defaulting to
`None` for backward compatibility) evaluates rules against the just-ingested samples.
Any exception from that step — typed (`PersistenceError`) or a genuine bug — is caught,
logged, and never allowed to fail the ingestion response.

**Alert Lifecycle**: exactly two states, `firing` and `resolved`.
- A breach with no existing open alert for `(node_id, rule_key)` → **opens** a new
  `firing` alert.
- A breach with an already-open alert → **advances** `last_fired_at`/`triggering_value`
  on the *same row* — this is the Phase 3 dedup ("don't open a duplicate row for an
  already-firing condition"), distinct from Phase 4's *notification-level* dedup
  ("don't re-notify Telegram every minute for a still-firing alert").
- No breach with an open alert → **resolves** it (`resolved_at` set).
- No breach with no open alert → no-op.

No `acknowledged`/`escalated` states, no manual resolve/acknowledge endpoint — those are
explicitly Phase 4 ("Telegram Alerts: Acknowledgement, Escalation, Deduplication").
Uniqueness of "one open alert per `(node_id, rule_key)`" is enforced at the application
level (`AlertEvaluationService`), not a database constraint — same precedent as
`NodeRepository.upsert_seen`'s get-then-write pattern (`docs/adr/003-heartbeat-deadman-switch.md`).

**Read API**: `GET /api/v1/alerts` (optional `?status=` filter) and
`GET /api/v1/alerts/{id}` — a judgment call (not explicitly named in `ROADMAP.md`), same
precedent as Phase 2 adding node-registry read endpoints: an alerting subsystem with no
way to observe it via the API isn't verifiable or useful yet.

## Alternatives Considered

- **Database-backed dynamic rule management (CRUD API)** — more flexible, allows
  per-fleet customization and hot-reload without a restart. Rejected for this phase:
  `ROADMAP.md` says "Threshold Rules"/"Rate-of-change Rules," not "Rule Management API";
  building CRUD + a new schema for rule definitions is scope beyond what's asked, and a
  static file is the simplest thing that actually satisfies the requirement.
- **Background scheduler periodically re-evaluating all nodes' recent data** — would
  also enable alerting on node staleness (silence, not just bad values), closing a gap
  this decision leaves open. Rejected for now: no scheduler exists in the Collector
  (`docs/adr/017-collector-sync-vs-async-db.md`'s same "no complexity without a
  demonstrated need" reasoning), and staleness-alerting was already explicitly deferred
  past Phase 2. Revisit together if any future phase needs a Collector-side background
  job for another reason.
- **Metrics-push doubles as the only rule-evaluation trigger, full stop, no lifecycle
  dedup** — i.e., open a new alert row every single breaching push. Rejected: would
  flood the alerts table with duplicate "still firing" rows for a metric that stays
  breached across many consecutive pushes, making the alerts list useless for answering
  "what's currently wrong."
- **Flap damping (require N consecutive breaches before firing)** — reduces alert churn
  on noisy/oscillating metrics. Rejected for this phase as unnecessary complexity beyond
  what "Alert Lifecycle" literally requires; documented as a known limitation instead of
  silently absent.

## Consequences

- Changing a rule requires editing the config file and restarting the Collector — no
  hot-reload, no per-tenant customization. Acceptable now; the natural trigger to revisit
  is a real operational need for dynamic rules.
- A node that stops pushing entirely is never re-evaluated — rule evaluation is coupled
  to ingestion, so silence produces no alert. This is a real, known gap (distinct from
  the existing `is_stale` *field*, which is computed but never acted on) until a
  scheduler is introduced.
- Alert churn under oscillating metrics (no flap damping) — an alert can open/resolve
  repeatedly across a noisy metric's consecutive pushes.
- A Rule Engine bug is invisible to the Agent and to the ingestion response by design —
  it only surfaces in Collector logs (`rule_evaluation_failed`). This is intentional
  (protects the ingestion contract) but means alerting failures need their own
  operational visibility (log monitoring), not HTTP-response monitoring.

## Interview Talking Points

The core tension is the same one that shows up in almost every rules/alerting system:
where do rule definitions live (static config vs. dynamic store), and how do you avoid an
alert list that's just a firehose of duplicate "still broken" notifications for one
ongoing problem. The dedup design here — advance the same row instead of creating a new
one — is the standard pattern (e.g., Prometheus Alertmanager's grouping, Nagios's
"already in this state" suppression) generalized to its simplest form: one open row per
`(entity, condition)` pair. Keeping rule *evaluation* synchronous with ingestion, rather
than adding the Collector's first background scheduler, was a deliberate scope
discipline call — it directly means staleness-based alerting isn't solved yet, and that
tradeoff is written down here rather than silently implied. Revisit the "config file vs.
database" choice specifically when multiple deployments need different rules from the
same codebase; revisit "no scheduler" when *any* other phase needs a Collector-side
background job, since paying that architectural cost once for two features is better than
paying it twice.
