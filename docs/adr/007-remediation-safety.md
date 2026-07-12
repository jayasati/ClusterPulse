# ADR-007: Remediation Safety

## Status

Accepted

_Implemented in `collector/remediation/` (`RemediationEngine`, `RemediationPolicy`),
`collector/config.py` (Safety Limit settings), `agent/config.py` (Agent-side opt-in and
allowlist), `shared/exceptions/remediation.py` (`RemediationSafetyError`), Phase 5._

## Context

`ROADMAP.md` Phase 5 names "Auto Remediation, Playbooks, Audit Logs, Safety Limits."
Auto-remediation is qualitatively different from every prior phase: it takes real action
on monitored infrastructure rather than only observing and notifying. This ADR was
pre-reserved at Phase 0 specifically because of that blast-radius difference, and commits
to addressing rate limits, blast-radius limits, dry-run/approval gates, and the role of
`RemediationSafetyError` as a first-class error category.

Two further constraints shaped the design, both surfaced during Phase 5's design
discussion and explicitly confirmed before implementation began:

- The Agent had zero command-execution capability before this phase (every collector in
  `agent/collectors/` only reads system state via `psutil`) — giving it one is a
  significant, security-sensitive capability addition, not an incremental change.
- The user explicitly chose to include real Agent-side execution in this phase, accepting
  the larger scope, rather than deferring execution to a follow-up phase and shipping only
  a decision/audit pipeline in dry-run mode.

## Decision

**Remediation is only ever considered once an alert has escalated**, reusing
`AlertEvaluationService`'s existing "still breaching, unacknowledged, past a time
threshold" check (`docs/adr/019-alert-acknowledgement-escalation.md`) rather than
inventing a parallel timing mechanism. A new `remediation_after_seconds` setting is
validated (`ConfigurationError` at startup) to be `>= escalation_after_seconds` whenever
remediation is enabled — automation never acts before a human has had a chance to.
Remediation is attempted **at most once per alert** (mirrors escalation's single-tier
pattern): `AlertRecord` gains a `remediated_at` column, set the first time a real decision
(dispatched *or* blocked) is recorded, so a disabled engine or an unmapped `rule_key`
never consumes the one-shot — a Playbook added later while the alert is still firing still
gets a chance.

**Playbooks are a small, explicit, config-file-driven catalog** (`collector/remediation/
default_playbooks.json`), mirroring the Rule Engine's static-config precedent
(`docs/adr/006-alert-lifecycle.md`) — never arbitrary command execution. Each entry maps
one `rule_key` to one named action (`playbook_name`, `action_type`, `parameters`). At most
one Playbook per `rule_key`, enforced at config-load time.

**Safety Limits are a hard gate evaluated before any dispatch, and are layered — not a
single check:**

1. A global kill switch, `remediation_enabled: bool = False` (Collector), off by default —
   stricter than Telegram's optional-but-on-by-configuration pattern
   (`docs/adr/018-telegram-notifications.md`), since this is the highest blast-radius
   feature in the project.
2. A per-node-per-hour rate limit (`max_remediations_per_node_per_hour`, default 3).
3. A cooldown since the last action for the same `(node_id, playbook_name)`
   (`remediation_cooldown_seconds`, default 1800s).
4. **A second, independent opt-in on the Agent itself** (`CLUSTERPULSE_AGENT_
   REMEDIATION_ENABLED`, also off by default) — even if the Collector dispatches an
   action, the Agent refuses to execute it unless its own configuration separately agrees.
   A compromised or misconfigured Collector cannot unilaterally cause execution.
5. **A local, Agent-side allowlist** for `CLEAR_DIRECTORY` targets
   (`CLUSTERPULSE_AGENT_REMEDIATION_ALLOWED_DIRECTORIES`) — checked independently of
   whatever the Collector's Playbook config says. The Agent never blindly trusts an
   instruction from the network; a path outside its own allowlist is refused and reported
   as `FAILED`, not attempted.

Every decision — dispatched or blocked — is recorded in a new `remediation_actions` table
(the audit log ROADMAP Phase 5 requires), with a status lifecycle
(`BLOCKED_BY_SAFETY_LIMIT`, `DISPATCHED`, `EXECUTED`, `FAILED`) distinct from `structlog`
output, queryable via `GET /api/v1/remediation-actions`.

**`RemediationSafetyError`** (`shared/exceptions/remediation.py`, cross-service since both
Collector and Agent raise it) is reserved for a *hard refusal* — an unsupported action
type, or an Agent-side allowlist violation — as opposed to a routine, expected
`BLOCKED_BY_SAFETY_LIMIT` decision, which is ordinary data, not an error.

**The Playbook catalog capable of real execution is deliberately narrower than the full
enum.** `NOOP` (exercises the pipeline with zero effect) and `CLEAR_DIRECTORY` (clears a
directory's contents, not the directory itself, entirely as the Agent's own unprivileged
user) are implemented. `RESTART_SERVICE` is a reserved enum value with no executor — see
`docs/adr/021-remediation-playbook-scope.md` for the full reasoning.

## Alternatives Considered

- **Ship only the decision/audit pipeline in dry-run mode this phase, defer real
  dispatch+execution to a follow-up** — the more conservative option, and my initial
  recommendation. Rejected once the user explicitly confirmed they wanted real execution
  in this phase, accepting the larger scope (dispatch mechanism, Agent privilege model,
  result reporting) that comes with it.
- **An independent remediation timer, not reusing the escalation gate** — would decouple
  remediation timing from escalation entirely. Rejected: reusing "has this escalated" as
  the sole trigger needs zero new timing concept, and encodes the safety property "a human
  gets a chance first" directly into the architecture rather than as a convention two
  independently-configured timers might drift out of.
- **A single global safety-limit check** (just the rate limit, no cooldown, no Agent-side
  opt-in/allowlist) — simpler, less code. Rejected: each layer defends against a distinct
  failure mode (rate limit bounds total action volume; cooldown prevents rapid re-fire on
  the same target; the Agent's independent opt-in defends against a compromised/
  misconfigured Collector; the Agent's allowlist defends against a misconfigured or
  malicious Playbook policy) — collapsing them would leave a real gap uncovered.
- **Marking `remediated_at` on every evaluation once past threshold, not just on a real
  decision** — simpler condition. Rejected: it would silently burn the one-shot for an
  alert that never actually got evaluated by an enabled engine with a mapped Playbook,
  making later configuration changes (enabling remediation, adding a Playbook) ineffective
  for already-firing alerts.

## Consequences

- Two independent, both-off-by-default opt-ins (Collector `remediation_enabled`, Agent
  `remediation_enabled`) means enabling real remediation end-to-end requires deliberate
  configuration on both sides — safe by default, never accidentally on.
- `RESTART_SERVICE` and any future privileged action requires its own future ADR covering
  the privilege/deployment model (running the Agent with elevated rights, or a scoped
  sudoers/polkit rule) — explicitly not solved here.
- No reconciliation for an action stuck at `DISPATCHED` if the Agent never responds (crash,
  network partition) — same root-cause gap as the pre-existing "no scheduler exists in the
  Collector" limitation already documented for staleness-alerting and escalation.
- No retry/buffering for a failed result report (unlike metrics, which buffer on the
  Agent) — a known, accepted limitation for this phase.

## Interview Talking Points

The interesting decision here wasn't "should remediation have safety limits" — obviously
yes — it was recognizing that a single safety check is the wrong shape for a
highest-blast-radius feature: each layer (global kill switch, rate limit, cooldown,
independent Agent-side opt-in, Agent-side allowlist) defends against a *different* actor
or failure mode, and defense-in-depth means the Agent — the component actually touching
the filesystem — never fully trusts the Collector's instruction, even though the Collector
is nominally the authority deciding what should happen. The other genuinely hard call was
scope: given the Agent had zero execution capability before this phase, "real
auto-remediation" could easily have ballooned into redesigning privilege boundaries for
every conceivable action. Scoping the real-execution catalog to what's achievable
unprivileged (`NOOP`, `CLEAR_DIRECTORY`) while explicitly reserving — not silently
dropping — `RESTART_SERVICE` for a dedicated future privilege-model ADR kept this phase
honest about what it actually solved versus what it deliberately left for later.
