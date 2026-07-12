# ClusterPulse Deployment

Two supported paths:

| Path | Use for | Entry point |
|---|---|---|
| Docker Compose | local dev, demos | `docker compose up --build` at the repo root |
| systemd installers | real Linux nodes | `deploy/install_collector.sh` / `deploy/install_agent.sh` |

## Docker Compose (dev/demo)

Brings up PostgreSQL 16, the Collector (with migrations applied on start),
one Agent, and Grafana:

```bash
docker compose up --build
# Collector API -> http://localhost:8000/healthz
# Grafana       -> http://localhost:3000  (admin/admin)
```

The compose stack uses fixed dev credentials (`dev-token`, `clusterpulse`,
`admin/admin`) on purpose — never reuse it beyond a laptop.

**Gotcha — pre-existing database volume**: PostgreSQL only runs
`docker-entrypoint-initdb.d` scripts when the data volume is *first*
created. If a `clusterpulse_pgdata` volume already exists from an earlier
run, the `clusterpulse_ro` role is never created and every Grafana panel
shows "No data" (its datasource login fails). Fix without wiping data:

```bash
docker compose exec -T db psql -U clusterpulse -d clusterpulse \
  < deploy/postgres/init-grafana-reader.sql
```

or start truly fresh with `docker compose down -v`.

## systemd install (production path)

On the Collector host (needs PostgreSQL reachable and `python3.13`):

```bash
sudo ./deploy/install_collector.sh
sudo vi /etc/clusterpulse/collector.env   # database URL, API tokens
sudo systemctl start clusterpulse-collector
```

On every monitored node:

```bash
sudo ./deploy/install_agent.sh
sudo vi /etc/clusterpulse/agent.env       # collector URL, auth token
sudo systemctl start clusterpulse-agent
```

Both installers are idempotent: re-running upgrades code and dependencies
but never overwrites an existing `/etc/clusterpulse/*.env`.

## Grafana

Provisioning lives in `deploy/grafana/`:

- `provisioning/datasources/clusterpulse.yaml` — PostgreSQL datasource
  connecting as the read-only `clusterpulse_ro` role
  (`deploy/postgres/init-grafana-reader.sql`). The password is injected via
  the `CLUSTERPULSE_GRAFANA_DB_PASSWORD` env var.
- `dashboards/` — three dashboards, loaded automatically:
  - **Cluster Overview** — fleet health: node count, staleness, firing
    alerts, ingest rate
  - **Node Detail** — per-node CPU / memory / disk / network time series
  - **Alerts & Remediation** — alert lifecycle table and the remediation
    audit log

For a non-Docker Grafana, point `provisioning` at these files (or copy
them into `/etc/grafana/provisioning/`) and set the env var.

## Retention

The Collector prunes aged data only when explicitly enabled
(`CLUSTERPULSE_COLLECTOR_RETENTION_ENABLED=true`). Defaults once enabled:
metric samples 7 days, resolved alerts 30 days, terminal remediation audit
rows 90 days, swept hourly in bounded batches. See
`docs/adr/010-retention-policy.md`.
