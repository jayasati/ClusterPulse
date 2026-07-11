# ADR-019: Alert Acknowledgement and Escalation

## Status

Accepted

_Implemented in `collector/services/alerting.py` (`AlertEvaluationService.acknowledge`,
escalation check folded into the existing "still breaching" path),
`collector/repositories/alert_repository.py` (`acknowledge_alert`, `escalate_alert`), and
`collector/db/migrations/versions/0003_alert_acknowledgement_escalation.py`, Phase 4._

## Context

`ROADMAP.md` Phase 4 names "Acknowledgement" and "Escalation" alongside "Telegram Alerts."
`docs/adr/006-alert-lifecycle.md` (Phase 3) deliberately left both out of the
`firing`/`resolved` state machine, reserving them for this phase. Two design questions had
to be resolved together: how acknowledgement relates to the existing two-state lifecycle,
and how escalation can work at all given the Collector has no scheduler
(`docs/adr/017-collector-sync-vs-async-db.md`, `docs/adr/011` in `.claude/DECISIONS.md`).

## Decision

**Acknowledgement is an orthogonal attribute, not a third `AlertStatus` value.**
`AlertModel`/`AlertRecord`/`AlertView` gain `acknowledged_at`/`acknowledged_by` (both
nullable, defaulting to `None` — existing Phase 3 construction call sites keep working
unmodified). `AlertStatus` stays exactly `{firing, resolved}`. An alert can be `firing`
*and* acknowledged simultaneously — acknowledging never changes its status, only
resolving (the rule no longer breaching) does. `POST /api/v1/alerts/{id}/acknowledge`
(body: `{"acknowledged_by": "<name>"}`) is idempotent while firing (re-acknowledging just
overwrites who/when — e.g. a shift handoff) and raises `AlertAlreadyResolvedError` (409)
if the alert has already resolved.

**Escalation is single-tier and piggybacks on the existing ingestion-triggered
evaluation**, exactly like rule evaluation itself. No new scheduler. Each time a
still-firing alert advances (`update_last_fired`), `AlertEvaluationService` additionally
checks: not acknowledged, not already escalated, and `now - first_fired_at >=
escalation_after_seconds` (default 900s / 15 minutes, configurable). If all hold, it sets
`escalated_at` (gating re-escalation — at most once per alert) and sends an escalation
notification. **Direct, stated consequence**: exactly like staleness-alerting
(`docs/adr/006-alert-lifecycle.md`), a firing alert on a node that stops pushing entirely
never escalates — the same limitation, now extended from "detection" to "escalation,"
not a new one.

**Acknowledgement suppresses escalation, not notification of the original alert or its
eventual resolution.** The whole point of acknowledging is "a human has claimed this,
stop nagging" — which specifically means "stop escalating," not "go silent forever."

## Alternatives Considered

- **A dedicated `acknowledged` `AlertStatus` value** — simpler read-API filtering in some
  respects (`?status=acknowledged`). Rejected: collapses two independent facts ("is the
  condition still true" and "has a human claimed it") into one field, which can't
  represent "acknowledged, still firing" and "acknowledged, now resolved" without either
  losing information or reintroducing a second field anyway. Industry precedent
  (PagerDuty, Opsgenie) treats these as orthogonal for exactly this reason.
- **A real scheduler for escalation, decoupled from ingestion** — the more "correct"
  design for time-based escalation (an alert should arguably escalate at exactly T+15m,
  not "whenever the node next happens to push"). Rejected for this phase: no scheduler
  exists in the Collector, and introducing one is a bigger architectural change than
  "Escalation" as one `ROADMAP.md` line item justifies on its own. Revisit if/when a
  scheduler is introduced for another reason (e.g., staleness alerting) — the two
  problems compound and are worth solving together.
- **Multi-tier escalation ladder** (e.g., 15m → 1h → 4h, possibly different chats per
  tier) — more expressive, closer to what mature on-call tooling offers. Rejected as
  scope beyond "Escalation" named once, singular, in `ROADMAP.md`; a single tier is the
  simplest thing that satisfies the requirement.
- **Verified acknowledger identity** — would require per-user credentials, which don't
  exist (`docs/adr/005-authentication.md`'s shared-token model). Rejected as out of
  scope; `acknowledged_by` stays a free-text, self-reported string, with the limitation
  stated plainly rather than papered over.
- **Un-acknowledging automatically on continued breach** — i.e., treat ack as temporary,
  expiring after some time so a long-ignored alert re-escalates anyway. Rejected:
  contradicts the entire purpose of single-tier escalation-then-stop; if this is wanted
  later, it's better modeled as a second escalation tier (see multi-tier alternative
  above) than as ack-expiry.

## Consequences

- Escalation and staleness-alerting now share the exact same architectural gap (both
  need a scheduler that doesn't exist) — documented together in
  `collector/architecture.md` Future Extension Notes so a future scheduler addition
  addresses both, not just one.
- `acknowledged_by` carries no verified identity — an audit trail exists (who *claimed* to
  acknowledge, and when), but not a verified one. Stated as a known limitation, same root
  cause as ADR-005's identity-spoofing gap.
- Single-tier escalation means "ignored for 16 minutes" and "ignored for 3 hours" look
  identical after the one escalation fires — no distinction, no further nagging.
- Three new nullable columns (`acknowledged_at`, `acknowledged_by`, `escalated_at`) via
  migration `0003` — purely additive, no risk to existing alert rows' semantics.

## Interview Talking Points

The acknowledgement-as-orthogonal-attribute vs. new-status question is a recurring
alerting-system design decision, and the deciding factor is always the same: does the
"is this actively wrong" fact and the "has a human responded" fact ever need to vary
independently? Here they clearly do (an operator can claim a still-breaching alert
without the underlying problem being fixed yet), so collapsing them into one enum would
have been the wrong call even though it looks simpler at first glance. The escalation
design is a more pointed scope-discipline story: the "correct" implementation (a
scheduler ticking on wall-clock time) was available in spirit but deliberately not built,
because this project has a standing architectural position (`docs/adr/017`) against
adding async/background-job complexity without a demonstrated need — and "Escalation" as
one `ROADMAP.md` bullet doesn't, by itself, meet that bar. The honest move was to ship the
ingestion-triggered approximation, name its limitation explicitly (silent nodes never
escalate), and flag it as the same gap staleness-alerting already has — rather than either
silently shipping a half-solution or over-building a scheduler two features are quietly
waiting to justify together.
