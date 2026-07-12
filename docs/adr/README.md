# Architecture Decision Records (ADR)

This directory contains all major architectural decisions made during the development of
ClusterPulse.

Each ADR explains:

- the problem
- possible alternatives
- tradeoffs
- final decision
- consequences

The purpose is to document *why* architectural decisions were made, making the system
easier to maintain, review, and extend.

## ADR Format

Every ADR follows the same structure (see [`000-template.md`](000-template.md)):

1. **Status** — `Proposed`, `Accepted`, `Superseded by ADR-xxx`, or `Rejected`
2. **Context** — the problem and the constraints that shaped it
3. **Decision** — what was decided
4. **Alternatives Considered** — what else was evaluated, and why it lost
5. **Consequences** — what this decision costs us or commits us to
6. **Interview Talking Points** — the trade-off framing worth being able to explain out loud

## Status legend

- **Accepted** — decided, current, and in effect.
- **Proposed** — placeholder for a decision that belongs to a phase not yet started
  (see `.claude/ROADMAP.md`). Structure is reserved now so numbering and cross-references
  stay stable; content is written when that phase begins, per the project rule of never
  designing/implementing more than one phase ahead.
- **Superseded** — replaced by a later ADR; the old ADR is kept for history and links
  forward to the one that replaced it.

## Index

| ADR | Title | Status |
|---|---|---|
| [000](000-template.md) | Template | — |
| [001](001-push-vs-pull.md) | Push vs. Pull metrics delivery | Accepted |
| [002](002-postgresql-choice.md) | PostgreSQL over InfluxDB | Accepted |
| [003](003-heartbeat-deadman-switch.md) | Heartbeat / dead-man switch | Accepted |
| [004](004-agent-buffering.md) | Agent local buffering | Accepted |
| [005](005-authentication.md) | Authentication | Accepted |
| [006](006-alert-lifecycle.md) | Alert lifecycle | Accepted |
| [007](007-remediation-safety.md) | Remediation safety | Accepted |
| [008](008-grafana-vs-custom-ui.md) | Grafana vs. custom UI | Accepted |
| [009](009-systemd-service.md) | systemd service packaging | Accepted |
| [010](010-retention-policy.md) | Retention policy | Accepted |
| [011](011-http-vs-message-queue.md) | HTTP vs. message queue | Accepted |
| [012](012-python-tech-stack.md) | Python tech stack | Accepted |
| [013](013-logging-strategy.md) | Logging strategy | Accepted |
| [014](014-deployment-strategy.md) | Deployment strategy | Proposed (Phase 7) |
| [015](015-testing-strategy.md) | Testing strategy | Proposed |
| [016](016-database-migration-strategy.md) | Database migration strategy | Accepted |
| [017](017-collector-sync-vs-async-db.md) | Collector sync vs. async DB access | Accepted |
| [018](018-telegram-notifications.md) | Telegram notifications | Accepted |
| [019](019-alert-acknowledgement-escalation.md) | Alert acknowledgement and escalation | Accepted |
| [020](020-remediation-dispatch-mechanism.md) | Remediation dispatch mechanism | Accepted |
| [021](021-remediation-playbook-scope.md) | Remediation Playbook scope (Phase 5) | Accepted |

ADRs 016+ were added during Phase 2+ for decisions that didn't map to a Phase-0-reserved
slot — the reserved numbering (000-015) covers what was foreseeable at Phase 0; new
numbers are appended as later phases surface decisions that weren't anticipated in advance.

See [`docs/architecture/00-project-initialization.md`](../architecture/00-project-initialization.md)
for the Phase 0 design document these accepted ADRs are drawn from.
