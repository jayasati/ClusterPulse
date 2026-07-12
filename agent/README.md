# Agent

The ClusterPulse Agent runs on every monitored Linux node. It collects local health
metrics (CPU, memory, disk, network) via `psutil` and pushes them to the Collector over
HTTP (`docs/adr/001-push-vs-pull.md`). Since Phase 5, it can also execute a small, fixed
catalog of remediation actions the Collector dispatches — disabled by default, gated by
its own independent opt-in (`docs/adr/007-remediation-safety.md`). See `architecture.md`
in this directory for the full design, sequence diagram, and class diagram.

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
| `CLUSTERPULSE_AGENT_REMEDIATION_ENABLED` | `false` | Independent opt-in to actually execute dispatched Playbooks — see `docs/adr/007-remediation-safety.md` |
| `CLUSTERPULSE_AGENT_REMEDIATION_ALLOWED_DIRECTORIES` | `""` | Comma-separated absolute paths this Agent may clear for `CLEAR_DIRECTORY` — checked independently of the Collector's Playbook config |
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod` — controls log rendering |
| `LOG_LEVEL` | `INFO` | Log level |

Invalid or missing required configuration fails process startup immediately (before any
collector, transport, or buffer is constructed) — see `docs/architecture/00-project-initialization.md` §4.

## Remediation

Disabled by default. When the Collector dispatches a Playbook, it rides the `Ack`
response to this Agent's own metrics push (`Ack.pending_actions`) — no separate poll (see
`docs/adr/020-remediation-dispatch-mechanism.md`). `AgentScheduler` then executes each
action via `PlaybookExecutor` **only if** `REMEDIATION_ENABLED=true` here — a second,
independent opt-in from the Collector's own, so a compromised or misconfigured Collector
cannot unilaterally cause execution. Only `NOOP` (no-op, always succeeds) and
`CLEAR_DIRECTORY` (deletes a directory's contents, not the directory itself) have
executors; `RESTART_SERVICE` is refused as unsupported (`docs/adr/021-remediation-playbook-scope.md`).

`CLEAR_DIRECTORY` additionally checks the dispatched path against
`REMEDIATION_ALLOWED_DIRECTORIES` — a path outside this Agent's own allowlist is refused
and reported `FAILED`, regardless of what the Collector's Playbook config said to
dispatch. After executing (or refusing), the Agent reports the result immediately via
`POST /api/v1/remediation-actions/{id}/result`; a failed report is logged and dropped, not
retried or buffered.

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
├── remediation/
│   ├── executor.py            PlaybookExecutor — dispatches to action handlers, never raises
│   └── actions/
│       ├── noop.py              execute_noop()
│       └── clear_directory.py   execute_clear_directory() — allowlist-checked
├── scheduler.py              AgentScheduler — sequential collection/delivery cycles,
│                               executes pending_actions from the current cycle's Ack
├── buffer.py                 FileBuffer — durable local buffer for undelivered payloads
└── transport/
    └── http_client.py        HttpTransport — push metrics + report remediation results
```

## Future extension notes

See `architecture.md` §Future Extension Notes for what later phases are expected to add
(authentication headers, multi-mount disk collection, async scheduling, a privileged
`RESTART_SERVICE` executor, retry/buffering for failed result reports).
