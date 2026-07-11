# Agent

The ClusterPulse Agent runs on every monitored Linux node. It collects local health
metrics (CPU, memory, disk, network) via `psutil` and pushes them to the Collector over
HTTP (`docs/adr/001-push-vs-pull.md`). See `architecture.md` in this directory for the
full design, sequence diagram, and class diagram.

## Running

```bash
python -m agent.main
```

The process runs until it receives `SIGINT`/`SIGTERM`, at which point it finishes its
current cycle and exits.

## Configuration

All settings are environment variables prefixed `CLUSTERPULSE_AGENT_`, or a local `.env`
file (see `shared/config/base.py` / `agent/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `CLUSTERPULSE_AGENT_NODE_ID` | local hostname | Identity this Agent reports to the Collector |
| `CLUSTERPULSE_AGENT_COLLECTOR_BASE_URL` | `http://localhost:8000` | Collector endpoint |
| `CLUSTERPULSE_AGENT_COLLECTION_INTERVAL_SECONDS` | `30.0` | Seconds between collection cycles |
| `CLUSTERPULSE_AGENT_HTTP_TIMEOUT_SECONDS` | `10.0` | Per-request HTTP timeout |
| `CLUSTERPULSE_AGENT_HTTP_RETRY_ATTEMPTS` | `3` | Bounded retry attempts for retryable failures |
| `CLUSTERPULSE_AGENT_BUFFER_PATH` | `./agent_buffer.jsonl` | Local durable buffer file |
| `CLUSTERPULSE_AGENT_BUFFER_MAX_ENTRIES` | `1000` | Buffer capacity before oldest-first eviction |
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod` — controls log rendering |
| `LOG_LEVEL` | `INFO` | Log level |

Invalid or missing required configuration fails process startup immediately (before any
collector, transport, or buffer is constructed) — see `docs/architecture/00-project-initialization.md` §4.

## Module layout

```
agent/
├── main.py                  Entrypoint: wiring + signal-based graceful shutdown
├── config.py                AgentSettings
├── collectors/               One psutil-based collector per metric family
│   ├── cpu.py
│   ├── memory.py
│   ├── disk.py
│   └── network.py
├── scheduler.py              AgentScheduler — sequential collection/delivery cycles
├── buffer.py                 FileBuffer — durable local buffer for undelivered payloads
└── transport/
    └── http_client.py        HttpTransport — push metrics to the Collector over HTTP
```

## Future extension notes

See `architecture.md` §Future Extension Notes for what Phase 2+ is expected to add here
(authentication headers, multi-mount disk collection, async scheduling).
