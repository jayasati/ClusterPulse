# ADR-009: systemd Units + Idempotent Shell Installers

## Status

Accepted (Phase 6)

## Context

Until Phase 6, "deployment" meant the hand-run provisioning used for the
live AWS verification, plus a `docker-compose.yml` broken since Phase 0
(wrong env-var names, port published on the wrong service, Dockerfiles
that did not exist). The ROADMAP's Phase 6 names "Installer."

## Decision

- **Production path: systemd.** `deploy/systemd/*.service` units run both
  processes as a dedicated non-login `clusterpulse` user with hardening
  (`NoNewPrivileges`, `ProtectSystem=strict`, explicit `ReadWritePaths`) —
  the Agent's unprivileged posture (`docs/adr/021-remediation-playbook-scope.md`) is now
  enforced by the unit, not just assumed.
- **Idempotent installers** (`deploy/install_collector.sh` /
  `install_agent.sh`): create the user, venv, and config template; apply
  migrations; enable units. Re-running upgrades code but never overwrites
  `/etc/clusterpulse/*.env`. Packaging (deb/rpm) is out of scope.
- **Docker Compose is the dev/demo path**, now actually functional: real
  Dockerfiles, correct `CLUSTERPULSE_*` env names, Collector owning port
  8000, Grafana + read-only DB role included, fixed dev credentials on
  purpose.

## Consequences

- A fresh Ubuntu 24.04 node goes from zero to enrolled with two commands
  (install script, edit env) — Phase 7's EC2 deployment exercise will
  validate the scripts end-to-end on real instances.
- Shell installers assume systemd Linux; other init systems are
  unsupported (documented, not detected).
- The Phase 0 `DATABASE_URL` mismatch listed in PROJECT.md's tech debt is
  resolved.
