# ADR-008: Grafana over a Custom UI, Reading PostgreSQL Directly

## Status

Accepted (Phase 6)

## Context

The ROADMAP's Phase 6 names "Grafana / Dashboards." The Collector exposes
read APIs for alerts, nodes, and remediation actions — but none for metric
time series, and building a query API just for dashboards would be a
second, weaker Grafana.

## Decision

- Grafana connects **directly to PostgreSQL** using its native datasource,
  as a dedicated read-only role (`clusterpulse_ro`, created by
  `deploy/postgres/init-grafana-reader.sql`). No collector code changes.
- Datasource and dashboards are **provisioned as code** under
  `deploy/grafana/` (three dashboards: Cluster Overview, Node Detail,
  Alerts & Remediation) and version-controlled next to the schema they
  query. A unit test (`tests/unit/deploy/test_grafana_provisioning.py`)
  guards JSON validity and datasource-UID consistency.
- Credentials are injected via environment
  (`CLUSTERPULSE_GRAFANA_DB_PASSWORD`), never committed.

## Consequences

- Zero new API surface and zero new dependencies; the read-only role caps
  the blast radius of any dashboard mistake at "can read monitoring data."
- Dashboards are **coupled to the schema**: a column rename breaks a
  panel. Accepted deliberately — the dashboards live in the same repo and
  change in the same PR as any migration, and the provisioning test plus
  code review are the guard rails.
- If an external consumer ever needs metrics programmatically, that is an
  API design decision of its own (with pagination, authz, contracts) —
  explicitly out of Phase 6 scope.
