# Shared

`shared` is the only package both the Agent and the Collector import. It has no
dependency on `agent` or `collector`, and no dependency on FastAPI or SQLAlchemy — see
`docs/architecture/00-project-initialization.md` §8 for why, and `architecture.md` in
this directory for the class diagram and dependency-direction rule this package exists to
enforce.

## Module layout

```
shared/
├── contracts/v1/metrics.py   The Agent -> Collector wire contract (Pydantic models)
├── config/base.py             BaseServiceSettings — common settings shape
├── exceptions/                 ClusterPulseError hierarchy
├── logging/setup.py            configure_logging() — structlog setup
├── protocols.py                 MetricCollector / Transport / MetricsBuffer Protocols
└── constants.py                  MetricType enum + named defaults (no magic numbers)
```

## Why this package exists

Agent and Collector must agree on the exact shape of the data pushed between them
(`docs/adr/001-push-vs-pull.md`). Rather than each side defining its own copy of that
shape and keeping them in sync by hand, both import the same `NodeMetricsPayload` class
from `shared.contracts.v1.metrics` — there is exactly one definition of the wire format.
See `docs/architecture/00-project-initialization.md` §9 for the full rationale.

## Rule enforced by this package

`shared` must never import from `agent` or `collector`. Its only third-party dependency
is `pydantic` (+ stdlib, + `structlog` for the logging module). This is what lets the
Agent stay lightweight — it never pulls in FastAPI or SQLAlchemy by way of a `shared`
import.
