# ADR-012: Python Tech Stack

## Status

Accepted

## Context

`.claude/CLAUDE.md` and `.claude/CODING_STANDARDS.md` mandate a specific stack
(Python 3.13, FastAPI, PostgreSQL, SQLAlchemy, Pydantic, httpx, psutil, pytest, Ruff,
Black, MyPy) and a set of engineering principles (SOLID, strong typing, explicit
interfaces, DI). Phase 0 (`docs/architecture/00-project-initialization.md`) had to turn
that mandate into a concrete per-component dependency split, since the Agent and Collector
have very different deployment profiles (§1.2 of that document: the Agent runs on
potentially many arbitrary Linux nodes and must stay lightweight; the Collector is a
single, centrally-operated FastAPI service).

## Decision

Adopt the mandated stack exactly as specified, split by component:

- **Agent**: `httpx`, `psutil`, `pydantic`, `pydantic-settings` only — no FastAPI, no
  SQLAlchemy.
- **Collector**: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary]`,
  `pydantic`, `pydantic-settings`, plus `alembic` for migrations (proposed addition, see
  design doc §3.1).
- **Shared**: `pydantic` only (no framework dependency), so it can be imported by the
  lightweight Agent without pulling in Collector-only weight.
- **Tooling** (all components): `pytest` + `pytest-asyncio`, `ruff`, `black`, `mypy`.

Full package-by-package rationale is in
`docs/architecture/00-project-initialization.md` §3.

## Alternatives Considered

- **Go for the Agent** — smaller static binaries and lower steady-state resource
  footprint on monitored nodes, which matters given the Agent runs fleet-wide. Rejected
  for this project: a two-language codebase increases the cost of keeping the Agent↔Collector
  contract (see `shared/contracts`) in sync and slows iteration during early phases; the
  Python dependency-footprint concern is instead addressed by strict dependency separation
  (Agent excludes FastAPI/SQLAlchemy entirely) rather than a language change.
- **Django (instead of FastAPI) for the Collector** — mature, batteries-included, but
  heavier and less async-native; its ORM would also compete with the SQLAlchemy choice
  already driven by ADR-002. Rejected per the existing `.claude/DECISIONS.md` ADR-001
  rationale (async support, ease of testing).
- **A non-relational store (e.g. MongoDB) instead of PostgreSQL** — superseded by ADR-002;
  not re-litigated here.

## Consequences

- Two separate dependency sets must be maintained and kept from cross-contaminating —
  currently tracked as an open item (design doc §12.3: splitting `pyproject.toml` into
  optional dependency groups so `docker/agent.Dockerfile` never installs FastAPI/SQLAlchemy).
  Until that split lands, this separation is enforced by convention/code review only.
- `shared` being framework-agnostic (Pydantic + stdlib only) means any future new contract
  or utility added there must justify itself without reaching for FastAPI or SQLAlchemy
  conveniences.
- MyPy is adopted incrementally strict (see `docs/architecture/00-project-initialization.md`
  §5) rather than `strict = true` from commit one, to avoid blocking early Phase 1/2 work
  on a full-strict baseline before there's real code to calibrate against.

## Interview Talking Points

The interesting trade-off isn't "why Python" (that's given) — it's how a single-language
monorepo avoids becoming a distributed monolith when one component (the Agent) has a much
tighter footprint budget than the other (the Collector). The answer here is dependency
discipline enforced at the package-declaration level (separate optional dependency groups,
a framework-agnostic `shared`), rather than reaching for a second language purely to get
a smaller binary. Revisit the Go-agent alternative only if Agent resource footprint on
constrained/edge nodes becomes a measured, real problem — not preemptively.
