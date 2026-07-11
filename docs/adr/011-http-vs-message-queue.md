# ADR-011: HTTP vs. Message Queue

## Status

Accepted

_Implemented in `agent/transport/http_client.py` (`HttpTransport`), Phase 1._

## Context

ADR-001 decided the Agent initiates delivery (push). This ADR is the separate question of
*mechanism*: a direct HTTP request/response to the Collector, vs. routing delivery through
an intermediary message broker (Kafka, RabbitMQ, NATS, etc.) that the Agent publishes to
and the Collector consumes from.

## Decision

The Agent delivers metrics via a direct HTTP POST to the Collector
(`HttpTransport.send`), using `httpx.Client` with a bounded, exponential-backoff retry
(`tenacity`) for retryable failures (timeouts, connection errors, 5xx responses). 4xx
responses raise immediately as non-retryable.

## Alternatives Considered

- **Message broker-mediated delivery** — decouples Agent and Collector lifecycles more
  fully (the broker durably queues messages even if the Collector is down for extended
  periods, and can fan out to multiple consumers later). Rejected for Phase 1: introduces
  an entire additional operational system (the broker itself — deployment, monitoring,
  backup, failure modes) before there's a demonstrated need for it. `agent/buffer.py`
  (`docs/adr/004-agent-buffering.md`) already gives the Agent side of "survive Collector
  downtime" without one.
- **gRPC instead of plain HTTP/JSON** — better wire efficiency and generated client/server
  stubs. Rejected: the Collector is FastAPI (ADR-001), which is natively HTTP/JSON-first;
  adding gRPC would mean running two protocol stacks on the Collector side for one
  Agent-facing endpoint, disproportionate to the payload sizes involved.

## Consequences

- Delivery is synchronous, request/response — the Agent blocks on each `send()` call
  (bounded by `http_timeout_seconds` and retry backoff), which is acceptable given the
  Agent's sequential, single-cycle-at-a-time scheduler (`docs/architecture/00-project-initialization.md`
  §5, `agent/architecture.md`).
- No fan-out: a message broker's natural "many consumers" capability isn't available if a
  future phase wants multiple systems to consume the same Agent stream (e.g., a
  Prometheus exporter reading the same feed independently of the Collector). If that need
  arises, it would most likely be solved at the Collector (re-publishing internally),
  not by revisiting this ADR.
- Retry/backoff logic lives in the Agent (`tenacity`) rather than being a broker's
  built-in guarantee — more code to test (see `tests/unit/agent/test_http_client.py`), but
  no broker-specific operational knowledge required to run the system.

## Interview Talking Points

This is a "do we need a broker yet" question, and the answer hinges on whether the
Collector's own downtime tolerance can be satisfied by the *client* buffering
(`docs/adr/004-agent-buffering.md`) rather than by a *durable intermediary*. For a
single-Collector, moderate-fleet-size system, client-side buffering plus bounded retry is
simpler to operate and reason about than a broker, at the cost of no fan-out and
synchronous per-request blocking. Revisit if either (a) the Collector needs to scale
beyond what a direct HTTP endpoint can absorb, or (b) more than one downstream system
needs to independently consume the same Agent metrics stream.
