# ADR-021: Remediation Playbook Scope (Phase 5)

## Status

Accepted

_Implemented in `collector/enums.py`/`shared/contracts/v1/remediation.py`
(`PlaybookActionType`), `agent/remediation/actions/` (`noop.py`, `clear_directory.py`),
Phase 5._

## Context

`PlaybookActionType` needs a catalog of action kinds both the Collector (deciding what to
dispatch) and the Agent (deciding whether to execute) agree on. The most commonly cited
real-world auto-remediation examples are restarting a hung/leaking service and reclaiming
disk space — but the Agent runs today as an ordinary unprivileged monitoring process
(`agent/collectors/` only ever reads via `psutil`), and `systemctl restart` (or equivalent)
almost always requires root or a scoped `sudo`/polkit rule the Agent does not have and
this phase does not provision.

## Decision

`PlaybookActionType` has three members, but only two have a real executor in Phase 5:

- **`NOOP`** — does nothing, reports success. Exists purely to exercise the full
  dispatch → execute → report pipeline end-to-end (in tests and in a live demo) with
  provably zero risk.
- **`CLEAR_DIRECTORY`** — deletes the contents of an allowlisted directory (not the
  directory itself). Requires no elevated privilege: it operates entirely within whatever
  the Agent's own unprivileged user can already write to. A real, useful action (reclaim
  disk space when a `disk.usage_percent` alert escalates) that needed no new privilege
  model to implement safely.
- **`RESTART_SERVICE`** — the enum value is reserved (referenced in configuration
  validation, e.g. `collector/remediation/definitions.py` explicitly rejects a Playbook
  that tries to use it) but **has no Agent-side executor**. Dispatching it is not possible
  because no `RemediationPolicy` can reference it — config validation fails fast at
  startup rather than allowing an unimplemented action into the audit log.

## Alternatives Considered

- **Implement `RESTART_SERVICE` too, running the Agent as root** — delivers the most
  commonly expected real-world remediation action. Rejected for this phase: running a
  monitoring agent as root is a significant, independent security posture change deserving
  its own dedicated ADR (weighing root vs. scoped `sudoers` rules vs. a privileged helper
  process), not something to fold in as a side effect of "add one more enum value."
- **Implement `RESTART_SERVICE` via a scoped `sudoers` rule** (e.g. `nginx_reload` only,
  no shell) — safer than full root, still requires deployment-time configuration (writing
  a sudoers file, choosing exactly which services are restartable) that has no home in
  this phase's scope and would need its own design/testing pass.
- **Drop `RESTART_SERVICE` from the enum entirely rather than reserving it** — simpler
  today. Rejected: the enum value documents the anticipated future extension in the type
  system itself (a Playbook config author sees it exists and discovers, via the
  fail-fast validation error, exactly why it isn't usable yet) rather than requiring
  someone to know to add it from scratch later.
- **A generic "run an arbitrary allowlisted shell command" action type** instead of named,
  narrow actions — more flexible, could express `RESTART_SERVICE`-like behavior without a
  dedicated code path. Rejected outright, independent of scope questions: this is close to
  a remote-code-execution primitive by construction, exactly the "arbitrary command
  execution" pattern `docs/adr/007-remediation-safety.md` explicitly rules out. Every
  Playbook action must be a specific, reviewed, narrowly-parameterized operation.

## Consequences

- Phase 5's real, working remediation story is disk-space reclamation, not service
  restart — a real but narrower capability than "auto-remediation" evokes in the
  abstract. Documented plainly rather than overstated.
- A future phase adding `RESTART_SERVICE` (or any privileged action) must design the
  privilege/deployment model first — this ADR's Consequences section is the marker for
  that future work, cross-referenced from `docs/adr/007-remediation-safety.md`.
- No deployment/packaging changes were needed for the Agent in this phase (still runs
  fully unprivileged) — a direct benefit of the narrower scope.

## Interview Talking Points

The temptation with "auto remediation" is to reach immediately for the flashiest example
(restart a service) without noticing it silently requires solving a much harder problem
(privilege escalation) first. The more disciplined move was separating "what action types
exist" from "what this phase can safely execute" — keeping `RESTART_SERVICE` in the type
system as a named, anticipated extension (so it's discoverable and its absence is a
deliberate, fail-fast-documented choice, not a silent gap) while only shipping executors
for actions that needed zero new privilege model. That distinction — reserved-but-not-
implemented vs. simply absent — is what let this phase deliver genuinely real execution
without quietly taking on a much larger security redesign it wasn't scoped or reviewed for.
