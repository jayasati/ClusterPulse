# ADR-015: Testing Strategy

## Status

Proposed — reserved; formalizes and supersedes the interim tooling notes in
`docs/architecture/00-project-initialization.md` §5 once ratified as its own decision.

## Context

_To be written before/during Phase 1._ `pytest` + `pytest-asyncio`, a `tests/unit` vs.
`tests/integration` split, and per-service test directories mirroring `agent/`,
`collector/`, `shared/` are already outlined in the Phase 0 design doc §2/§5 as a working
default. This ADR should formally ratify (or revise) that structure, plus decide coverage
gating thresholds and the fixture/mocking strategy for the Agent↔Collector HTTP boundary
(`pytest-httpx`/`respx`, per design doc §3.1) once there is real code to calibrate against.

## Decision

_Deferred._

## Alternatives Considered

_Deferred._

## Consequences

_Deferred._

## Interview Talking Points

_Deferred._
