# ADR-005: Authentication

## Status

Accepted

_Implemented in `collector/api/deps.py` (`verify_api_token`) and `collector/config.py`
(`CollectorSettings.token_set`), Phase 2. Agent-side support (sending the token) added in
`agent/config.py` / `agent/transport/http_client.py`._

## Context

The push model (`docs/adr/001-push-vs-pull.md`) means the Collector accepts inbound
requests from potentially many Agents. Without authentication, anyone who can reach the
Collector's network address can push arbitrary data or read the node registry. This ADR
was left open in Phase 0 specifically to resolve "per-node credentials vs. a shared fleet
token" once the Collector API existed to authenticate requests to.

## Decision

**Shared fleet token(s)**, not per-node credentials:

- `CollectorSettings.api_tokens` is a comma-separated string of valid bearer tokens,
  exposed as `token_set: frozenset[str]`.
- Every protected route depends on `verify_api_token` (`collector/api/deps.py`), which
  extracts the `Authorization: Bearer <token>` header via FastAPI's `HTTPBearer` and
  checks it against `token_set` using `hmac.compare_digest` per candidate token — a
  constant-time comparison, so response timing can't leak which prefix of a token is
  correct.
- **Environment-gated fail-fast**: an empty `token_set` is only permitted when
  `environment == "dev"`. In `staging`/`prod`, `CollectorSettings()` construction raises
  `ConfigurationError` immediately — the Collector cannot boot unauthenticated outside
  local development.
- `GET /healthz` is deliberately the one unauthenticated route — orchestrators/load
  balancers polling it shouldn't need a credential.
- Agent-side: `AgentSettings.auth_token` (default `None`) is sent as
  `Authorization: Bearer <token>` by `HttpTransport` when set; when unset, no
  `Authorization` header is sent at all — identical to pre-Phase-2 behavior.

## Alternatives Considered

- **Per-node credentials** (a distinct token or client certificate per Agent, checked
  against the node's claimed identity) — the stronger option, and the natural long-term
  answer once TLS/mTLS is in place (`.claude/PROJECT.md` Future Features). Rejected for
  Phase 2: requires a credential-provisioning and rotation story (who issues a node its
  credential, how, and how is it rotated) that doesn't exist yet and isn't in
  `ROADMAP.md` Phase 2. Building it now would mean designing a provisioning workflow
  under time pressure rather than deliberately in a dedicated phase.
- **No authentication in Phase 2, add it later** — rejected outright: shipping a
  publicly-writable metrics ingestion endpoint, even temporarily, is not "production
  quality" (`.claude/CLAUDE.md`) and there's no reason to defer something this
  foundational when the API is being built for the first time anyway.
- **API keys via query string** instead of a header — rejected: query strings routinely
  end up in access logs, browser history, and proxy logs; a header is the conventional,
  lower-exposure choice for credentials.
- **mTLS (client certificates)** — stronger than bearer tokens and would also solve
  identity binding, but requires a certificate authority and distribution story that's
  explicitly bundled with the future "TLS" item in `.claude/PROJECT.md`, not Phase 2.

## Consequences

- **Known limitation, stated plainly**: any request bearing a valid token authenticates
  as "a legitimate Agent," full stop — there is no check that the `node_id` a payload
  claims actually belongs to whoever holds that token. A leaked token lets an attacker
  push data under any node identity they choose. This is a direct, accepted consequence of
  choosing simplicity over per-node identity binding; it is not a bug to be fixed within
  Phase 2's scope.
- Token rotation means updating `CLUSTERPULSE_COLLECTOR_API_TOKENS` and restarting the
  Collector (or, since it's a set, adding the new token alongside the old one during a
  rollover window, then removing the old one) — there's no in-band rotation API.
- Every protected route pays the cost of one dependency resolution + a linear scan over
  `token_set` per request — negligible at the number of tokens a fleet-wide shared-secret
  model implies (a handful, not thousands).

## Interview Talking Points

The real trade-off is provisioning complexity vs. identity assurance. Per-node credentials
give you "this specific node is who it says it is," which shared tokens fundamentally
cannot — but per-node credentials only pay off once you also have a way to issue, store,
and rotate them per node, which is a project of its own. Shipping a shared-token model
now, with the spoofing limitation documented rather than hidden, is the same judgment call
many systems make in their first authenticated release (basic-auth-style shared secrets
before a full identity provider exists). The condition for revisiting this: either TLS/RBAC
lands (making per-node client certs a natural fit) or there's a real incident/threat model
that makes identity-spoofing an unacceptable risk before then.
