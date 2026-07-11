# Collector

The ClusterPulse Collector is the central FastAPI service that Agents push metrics and
heartbeats to (`docs/adr/001-push-vs-pull.md`), persists them to PostgreSQL
(`docs/adr/002-postgresql-choice.md`), and maintains the node registry. See
`architecture.md` in this directory for the full design, sequence diagrams, and class
diagram.

## Running

```bash
uvicorn collector.main:app --host 0.0.0.0 --port 8000
# or, for local convenience:
python -m collector.main
```

Apply migrations before first use:

```bash
alembic upgrade head
```

## Configuration

Environment variables prefixed `CLUSTERPULSE_COLLECTOR_`, or a local `.env` file (see
`shared/config/base.py` / `collector/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `CLUSTERPULSE_COLLECTOR_DATABASE_URL` | `postgresql+psycopg://clusterpulse:clusterpulse@localhost:5432/clusterpulse` | SQLAlchemy database URL |
| `CLUSTERPULSE_COLLECTOR_HOST` | `0.0.0.0` | Bind host (used by `python -m collector.main`) |
| `CLUSTERPULSE_COLLECTOR_PORT` | `8000` | Bind port |
| `CLUSTERPULSE_COLLECTOR_API_TOKENS` | `""` | Comma-separated bearer tokens. Empty is only allowed when `ENVIRONMENT=dev` — see `docs/adr/005-authentication.md` |
| `CLUSTERPULSE_COLLECTOR_HEARTBEAT_STALE_AFTER_SECONDS` | `90.0` | Dead-man-switch threshold — see `docs/adr/003-heartbeat-deadman-switch.md` |
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod` — also gates the auth-token fail-fast rule |
| `LOG_LEVEL` | `INFO` | Log level |

## API surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/metrics` | required | Ingest a metrics payload (the Agent's push target) |
| `POST` | `/api/v1/heartbeat` | required | Lightweight liveness ping (not yet called by the Agent) |
| `GET` | `/api/v1/nodes` | required | List every known node and its staleness |
| `GET` | `/api/v1/nodes/{node_id}` | required | Get one node (404 if never seen) |
| `GET` | `/healthz` | none | DB-connectivity liveness/readiness check |

## Module layout

```
collector/
├── main.py                    create_app() factory + module-level `app`
├── config.py                   CollectorSettings
├── exceptions.py                NodeNotFoundError
├── api/
│   ├── deps.py                   DI providers (settings, DB session, auth, services)
│   ├── error_handlers.py         ClusterPulseError subclasses -> HTTP responses
│   ├── schemas.py                 NodeRead (Collector's own read-API model)
│   └── routes/{metrics,heartbeat,nodes,health}.py
├── db/
│   ├── base.py                    declarative Base
│   ├── session.py                  engine/sessionmaker factory
│   ├── models/{node,metric_sample}.py
│   └── migrations/                 Alembic (see docs/adr/016-database-migration-strategy.md)
├── repositories/
│   ├── protocols.py                 NodeRepository, MetricsRepository (Protocols)
│   ├── node_repository.py            SqlAlchemyNodeRepository
│   └── metrics_repository.py         SqlAlchemyMetricsRepository
└── services/
    ├── node_registry.py              NodeRegistryService
    └── metrics_ingestion.py           MetricsIngestionService
```

## Future extension notes

See `architecture.md` §Future Extension Notes for what Phase 3+ is expected to add
(per-node credentials, async DB access if throughput demands it, alerting on stale nodes).
