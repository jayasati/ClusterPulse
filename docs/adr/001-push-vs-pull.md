# ADR-001: Push vs. Pull Metrics Delivery

## Status

Accepted

_Supersedes the informal decision recorded as "ADR-002" in `.claude/DECISIONS.md`._

## Context

ClusterPulse monitors a fleet of Linux nodes that are not necessarily on a uniform,
centrally-reachable network — nodes may sit behind NAT, in different subnets, or behind
firewalls that don't permit unsolicited inbound connections from a central Collector.
The Collector needs a reliable, operationally simple way to receive health/metric data
from every Agent instance (`.claude/ROADMAP.md` Phase 1 "HTTP Client" / Phase 2
"Heartbeat").

## Decision

The Agent initiates outbound HTTP connections and **pushes** metrics/heartbeat data to the
Collector. The Collector never initiates a connection to an Agent.

## Alternatives Considered

- **Collector polls Agents (pull model, à la Prometheus scrape)** — requires the Collector
  to know every Agent's reachable address and requires every Agent to accept inbound
  connections. Rejected: breaks down as soon as Agents are behind NAT/firewalls or on
  dynamic addresses, which is the expected deployment shape for this project.
- **Pull with service discovery (Consul/etcd-backed target registry)** — solves the
  addressing problem but adds a service-discovery dependency and operational surface
  disproportionate to this project's current scale. Rejected for now; revisit if Agent
  fleet size or network topology complexity grows enough to justify it.
- **Message queue-mediated delivery (Agent publishes, Collector consumes)** — considered
  and deferred to ADR-011, since it's a separate question (transport mechanism) layered on
  top of this one (direction of initiation).

## Consequences

- The Collector must accept and authenticate inbound requests from potentially many Agents
  (auth mechanism deferred to ADR-005).
- Because the Collector can't reach out to check on an Agent, "is this node still alive"
  must be inferred from the absence of expected pushes — this requires an explicit
  heartbeat / dead-man-switch design (ADR-003), rather than a failed-poll signal.
- If the Collector is unreachable, the Agent must not silently drop data — it needs local
  durable buffering and retry (ADR-004) rather than assuming the next poll will succeed.
- Firewall/NAT configuration for deployment is simpler: only one direction, one port, on
  the Collector side, needs to be reachable.

## Interview Talking Points

This is the same push-vs-pull trade-off seen across the industry: Prometheus's pull/scrape
model vs. the Datadog Agent's push model. Pull gives you free liveness detection (a failed
scrape *is* the down signal) and centralized target configuration; push gives you simpler
network topology and NAT traversal, at the cost of needing your own heartbeat/dead-man-switch
mechanism and inbound auth. We chose push because ClusterPulse's deployment target (many,
possibly NAT'd Linux nodes) makes "the Collector must be able to reach every Agent" the
harder constraint to satisfy, not the easier one. Revisit if ClusterPulse ever runs
exclusively inside a single flat, fully-routable network where pull's operational
simplicity (no heartbeat logic needed) would dominate.
