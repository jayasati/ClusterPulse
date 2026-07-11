# Collector

The ClusterPulse Collector is the central FastAPI service that Agents push metrics and
heartbeats to (`docs/adr/001-push-vs-pull.md`), persists them to PostgreSQL
(`docs/adr/002-postgresql-choice.md`), maintains the node registry, and evaluates
Threshold/Rate-of-change rules to raise and resolve alerts (`docs/adr/006-alert-lifecycle.md`).
See `architecture.md` in this directory for the full design, sequence diagrams, and class
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
| `CLUSTERPULSE_COLLECTOR_RULES_CONFIG_PATH` | `collector/rules/default_rules.json` | Path to the Threshold/Rate-of-change rules config — see `docs/adr/006-alert-lifecycle.md` |
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod` — also gates the auth-token fail-fast rule |
| `LOG_LEVEL` | `INFO` | Log level |

## API surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/metrics` | required | Ingest a metrics payload (the Agent's push target); also triggers rule evaluation |
| `POST` | `/api/v1/heartbeat` | required | Lightweight liveness ping (not yet called by the Agent) |
| `GET` | `/api/v1/nodes` | required | List every known node and its staleness |
| `GET` | `/api/v1/nodes/{node_id}` | required | Get one node (404 if never seen) |
| `GET` | `/api/v1/alerts` | required | List alerts, optionally filtered by `?status=firing\|resolved` |
| `GET` | `/api/v1/alerts/{alert_id}` | required | Get one alert (404 if it doesn't exist) |
| `GET` | `/healthz` | none | DB-connectivity liveness/readiness check |

## Rule configuration

Threshold and Rate-of-change rules are defined in a JSON file (default:
`collector/rules/default_rules.json`), loaded once at startup — not a database, not
hot-reloadable. See `docs/adr/006-alert-lifecycle.md` for why. Example:

```json
{
  "threshold_rules": [
    {
      "metric_type": "cpu.usage_percent",
      "comparison": "gt",
      "threshold": 90.0,
      "severity": "critical",
      "description": "CPU usage above 90%"
    }
  ],
  "rate_of_change_rules": [
    {
      "metric_type": "cpu.usage_percent",
      "comparison": "gt",
      "max_delta": 30.0,
      "window_seconds": 300.0,
      "severity": "warning",
      "description": "CPU usage increased by more than 30 percentage points within 5 minutes"
    }
  ]
}
```

At most one threshold rule and one rate-of-change rule per `metric_type` — a duplicate
fails Collector startup with `ConfigurationError`.

## Module layout

```
collector/
├── main.py                    create_app() factory + module-level `app`
├── config.py                   CollectorSettings
├── enums.py                     RuleKind, AlertStatus (shared by rules/ and repositories/)
├── exceptions.py                 NodeNotFoundError, AlertNotFoundError
├── api/
│   ├── deps.py                   DI providers (settings, DB session, auth, services)
│   ├── error_handlers.py         ClusterPulseError subclasses -> HTTP responses
│   ├── schemas.py                 NodeRead, AlertRead (Collector's own read-API models)
│   └── routes/{metrics,heartbeat,nodes,alerts,health}.py
├── db/
│   ├── base.py                    declarative Base
│   ├── session.py                  engine/sessionmaker factory
│   ├── timeutil.py                  ensure_utc() — SQLite naive-datetime normalization
│   ├── models/{node,metric_sample,alert}.py
│   └── migrations/                 Alembic (see docs/adr/016-database-migration-strategy.md)
├── rules/
│   ├── definitions.py               ComparisonOperator, Threshold/RateOfChange rule models, RulesConfig
│   ├── loader.py                     load_rules_config()
│   ├── default_rules.json             shipped sane defaults
│   └── engine.py                      RuleEngine, RuleEvaluationResult
├── repositories/
│   ├── protocols.py                 Node/Metrics/Alert Repositories + records (Protocols)
│   ├── node_repository.py            SqlAlchemyNodeRepository
│   ├── metrics_repository.py         SqlAlchemyMetricsRepository (write + rate-of-change read)
│   └── alert_repository.py           SqlAlchemyAlertRepository
└── services/
    ├── node_registry.py              NodeRegistryService
    ├── alerting.py                    AlertEvaluationService, AlertView
    └── metrics_ingestion.py           MetricsIngestionService (ingestion + best-effort rule evaluation)
```

## Future extension notes

See `architecture.md` §Future Extension Notes for what later phases are expected to add
(per-node credentials, async DB access if throughput demands it, Telegram delivery,
acknowledgement/escalation, dynamic rule management, flap damping).
