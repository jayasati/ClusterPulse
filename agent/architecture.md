# Agent — Architecture

Related: `docs/architecture/00-project-initialization.md` (project-wide design),
`docs/adr/001-push-vs-pull.md`, `docs/adr/004-agent-buffering.md`,
`docs/adr/011-http-vs-message-queue.md`, `docs/adr/012-python-tech-stack.md`,
`docs/adr/007-remediation-safety.md`, `docs/adr/020-remediation-dispatch-mechanism.md`,
`docs/adr/021-remediation-playbook-scope.md`.

## Overview

The Agent is a single-threaded, sequential process: one collection-and-delivery cycle
runs to completion before the next begins. There is no concurrency inside a cycle, and no
overlap between cycles — a slow cycle simply delays the next tick rather than running
alongside it. This keeps the Agent's dependency footprint and runtime model deliberately
simple (`docs/adr/012-python-tech-stack.md`): `httpx` + `psutil` + `pydantic` only, no
FastAPI or SQLAlchemy.

## Class diagram

```mermaid
classDiagram
    class AgentSettings {
        +node_id: str
        +collector_base_url: str
        +collection_interval_seconds: float
        +buffer_path: str
        +buffer_max_entries: int
    }

    class AgentScheduler {
        -node_id: str
        -collectors: list~MetricCollector~
        -transport: Transport
        -buffer: MetricsBuffer
        -interval_seconds: float
        -executor: PlaybookExecutor
        +run_once()
        +run_forever(should_stop)
    }

    class MetricCollector {
        <<Protocol>>
        +collect() list~MetricSample~
    }
    class CpuCollector
    class MemoryCollector
    class DiskCollector
    class NetworkCollector

    class Transport {
        <<Protocol>>
        +send(payload) Ack
        +report_action_result(action_id, result)
    }
    class HttpTransport {
        -client: httpx.Client
        +send(payload) Ack
        +report_action_result(action_id, result)
        +close()
    }

    class PlaybookExecutor {
        -allowed_directories: frozenset~str~
        +execute(action) ActionResult
    }

    class MetricsBuffer {
        <<Protocol>>
        +enqueue(payload)
        +drain(max_items) list~NodeMetricsPayload~
    }
    class FileBuffer {
        -path: Path
        -max_entries: int
    }

    MetricCollector <|.. CpuCollector
    MetricCollector <|.. MemoryCollector
    MetricCollector <|.. DiskCollector
    MetricCollector <|.. NetworkCollector
    Transport <|.. HttpTransport
    MetricsBuffer <|.. FileBuffer

    AgentScheduler --> MetricCollector : uses
    AgentScheduler --> Transport : uses
    AgentScheduler --> MetricsBuffer : uses
    AgentScheduler --> PlaybookExecutor : uses (optional — None unless remediation_enabled)
    AgentSettings --> AgentScheduler : configures (via agent.main.build_scheduler)
```

`MetricCollector`, `Transport`, and `MetricsBuffer` are `Protocol`s defined in
`shared/protocols.py` — `AgentScheduler` depends only on those abstractions
(Dependency Inversion), never on the concrete `Http Transport`/`FileBuffer`/collector
classes directly. This is what makes it possible to unit test the scheduler with fakes
(see `tests/unit/agent/test_scheduler.py`) with no network or filesystem I/O.

## Sequence diagram — one collection cycle

```mermaid
sequenceDiagram
    participant S as AgentScheduler
    participant B as MetricsBuffer
    participant C as MetricCollector(s)
    participant T as Transport
    participant Col as Collector (Phase 2, external)

    Note over S: run_once()
    S->>B: drain(DEFAULT_BUFFER_DRAIN_BATCH_SIZE)
    B-->>S: [buffered payloads]
    loop each buffered payload
        S->>T: send(payload)
        alt success
            T-->>S: Ack
        else FatalTransportError
            T-->>S: raises
            Note over S: logged, dropped (not re-enqueued)
        else RetryableTransportError
            T-->>S: raises
            Note over S: re-enqueue this + all remaining drained items, stop draining
            S->>B: enqueue(remaining)
        end
    end

    S->>C: collect() (per collector, isolated try/except)
    C-->>S: list[MetricSample] (or logged error, cycle continues)
    Note over S: build NodeMetricsPayload

    S->>T: send(payload)
    T->>Col: POST /api/v1/metrics
    alt 2xx
        Col-->>T: Ack(pending_actions=[...])
        T-->>S: Ack
    else 5xx / timeout / connection error
        Note over T: RetryableTransportError, retried with bounded backoff
        T-->>S: raises after exhausting retries
        S->>B: enqueue(payload)
    else 4xx
        Note over T: FatalTransportError, no retry
        T-->>S: raises
        Note over S: logged, dropped (not buffered)
    end

    opt Ack carried pending_actions and executor is configured
        loop each PendingAction
            S->>Executor: execute(action)
            Executor-->>S: ActionResult (EXECUTED or FAILED, never raises)
            S->>T: report_action_result(action_id, result)
            alt report fails (TransportError)
                T-->>S: raises
                Note over S: logged, dropped — not retried/buffered
            end
        end
    end
```

Pending actions are only executed for the *current* cycle's fresh delivery (the `send`
call in this diagram) — not for the buffered-payload redelivery loop above it, whose
`Ack` responses are received but not inspected for `pending_actions`. See
`docs/adr/020-remediation-dispatch-mechanism.md`.

## Design rationale (why sequential, not async)

`psutil` calls are blocking anyway, and there is exactly one Collector target per Agent —
concurrency inside a cycle would add complexity (thread/async safety in the buffer file,
overlapping cycle handling) without a corresponding benefit at this scale. See
`docs/architecture/00-project-initialization.md` §5 tradeoffs.

## Failure modes handled here

See `docs/architecture/00-project-initialization.md` §10 and the Phase 1 design
conversation for the full table. Summary: a single failing collector never blocks the
others; a down Collector triggers bounded retry then buffering; a buffer write/read
failure is logged and treated as empty/dropped rather than crashing the process; a
malformed-payload rejection (4xx) is dropped rather than retried forever.

## Future Extension Notes

- **Authentication** (`docs/adr/005-authentication.md`, Phase 2): `HttpTransport` will
  need a header-injection seam for a bearer token / mTLS client cert — currently sends
  unauthenticated requests.
- **Multi-mount disk collection**: `DiskCollector` currently monitors a single configured
  mount point (default `/`). Monitoring multiple mounts would mean either multiple
  `DiskCollector` instances (one per mount, no code change needed — it already accepts a
  `mount_path` constructor argument) or a `DiskCollector` that iterates
  `psutil.disk_partitions()`.
- **Async scheduler**: if the Agent ever needs to collect from many independent targets
  concurrently (unlikely for a single-node Agent, more plausible for a future
  "supervisor" mode), the sequential model here would need revisiting — not a Phase 1
  concern.
- **Stronger node identity** (`docs/adr/003-heartbeat-deadman-switch.md`, Phase 2):
  hostname-based `node_id` is not collision-proof across cloned VM images; a
  generated-and-persisted UUID is the likely successor.
- **Heartbeat**: Phase 2's dead-man-switch design may add a lightweight heartbeat-only
  push (distinct from a full metrics payload) on a separate, shorter interval.
- **A privileged `RESTART_SERVICE` executor** (Phase 5): needs its own privilege model
  (root, scoped sudoers/polkit, or a privileged helper process) — see
  `docs/adr/021-remediation-playbook-scope.md`. `PlaybookExecutor` is already structured
  so a new `agent/remediation/actions/` handler is additive, not a redesign.
- **Retry/buffering for failed remediation result reports** (Phase 5): currently logged
  and dropped on failure, unlike metrics payloads which buffer via `FileBuffer`.
- **Executing pending actions from buffered/redelivered payloads** (Phase 5): currently
  only the current cycle's fresh delivery triggers execution — a deliberate scope
  boundary for this phase, not a hard architectural limit.
