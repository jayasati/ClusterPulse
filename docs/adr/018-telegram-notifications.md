# ADR-018: Telegram Notifications

## Status

Accepted

_Implemented in `collector/notifications/` (`Notifier`, `TelegramNotifier`,
`formatting.py`), Phase 4._

## Context

`ROADMAP.md` Phase 4 names "Telegram Alerts" as its first item. Unlike Phase 2/3, nothing
in the original Phase-0-reserved ADR set (`000`-`015`) anticipated a notification channel
— this decision needed a new number, same as `016`/`017` did in Phase 2. The Alert
Lifecycle (`docs/adr/006-alert-lifecycle.md`) already produces `firing`/`resolved` alert
records; this ADR is about how a human finds out about them.

## Decision

- **Channel**: Telegram Bot API, via a direct `httpx` POST to
  `https://api.telegram.org/bot{token}/sendMessage` — no new dependency (`httpx` is
  already used by the Agent's `HttpTransport`).
- **Delivery guarantee: fire-and-forget, single attempt, never raises.**
  `TelegramNotifier.notify(message) -> bool` catches every failure (network error,
  timeout, non-2xx response) internally, logs it, and returns `False` — it never
  propagates an exception to its caller. The alert's state is already durably persisted
  in Postgres *before* `notify()` is ever called, so a Telegram outage costs only the
  notice, never the record of what happened.
- **Notify on transitions only, not every evaluation.** A message is sent when an alert
  opens, escalates, or resolves — never on the "still firing, unchanged" advance that
  happens on every subsequent breaching push (roughly every 30s per node, by the Agent's
  default collection interval). This is the Phase 4 notification-level dedup ADR-011
  explicitly deferred, distinct from the row-level dedup (one open alert per
  `(node_id, rule_key)`) Phase 3 already built.
- **Optional, not fail-fast.** `telegram_bot_token`/`telegram_chat_id` default to `None`;
  if unset, notifications are silently disabled (`Notifier` is `None`, no log noise).
  Unlike `api_tokens` (`docs/adr/005-authentication.md`), there's no security reason to
  force this to be configured outside `dev` — missing notifications is a functionality
  gap, not a security hole. The one validation applied: if exactly one of the two
  settings is set, `CollectorSettings` raises `ConfigurationError` at startup (catches an
  almost-certain typo/misconfiguration without being a blanket fail-fast rule).
- **Notifier is a `Protocol`**, constructed once at Collector startup (like the DB engine
  and session factory) rather than per-request, so it reuses one HTTP connection pool.
  `AlertEvaluationService` depends on `Notifier`, never on `TelegramNotifier` concretely —
  a second channel (email, Slack, PagerDuty) is additive later, not a redesign.

## Alternatives Considered

- **Retry-with-backoff, mirroring the Agent's `HttpTransport`** — stronger delivery
  guarantee for the notification itself. Rejected: the Agent retries because losing a
  metrics push means losing data with no other record of it; losing a Telegram
  notification loses nothing durable — the alert row is the source of truth and is
  already safely written. Adding retry/backoff machinery to protect a best-effort notice
  is complexity without a corresponding durability gain.
- **A message queue between alert evaluation and notification delivery** — would let a
  transient Telegram outage be retried later without re-running rule evaluation.
  Rejected for the same reason ADR-011 rejected a message broker for Agent delivery: no
  operational component exists yet to justify the complexity, and the thing being
  protected (a notice, not data) doesn't need it.
- **Notify on every evaluation, let Telegram's own rate limiting handle the noise** —
  simpler code (no transition-tracking logic). Rejected outright: would send a message
  roughly every 30 seconds for every still-firing alert, which is both spammy and a real
  risk of hitting Telegram's per-chat rate limits under normal operation, not just at
  fleet-wide-incident scale.
- **A dedicated background worker for notification delivery** — decouples notification
  latency from the request/response cycle. Rejected: adds a queue and worker process
  neither `ROADMAP.md` nor the existing architecture calls for; the synchronous call adds
  at most one HTTP round-trip (bounded by a short timeout) to the ingestion request,
  which is acceptable given `MetricsIngestionService` already isolates rule-evaluation
  failures from the response.

## Consequences

- A Telegram message lost to a transient outage is genuinely lost — not queued, not
  retried. Acceptable because the alert record itself was never at risk.
- No dependency on Telegram-specific message formatting beyond `sendMessage`'s plain
  `text` field — no rich formatting (Markdown/HTML), buttons, or interactive
  acknowledgement-from-Telegram. Acknowledgement is done via the API (`docs/adr/019-alert-acknowledgement-escalation.md`),
  not a Telegram button, keeping this ADR's scope to delivery only.
- A fleet-wide incident opening many alerts simultaneously could approach Telegram's
  rate limits (no batching/throttling implemented) — noted as a real gap, not solved.
- `Notifier`'s "never raises" contract is a discipline the real implementation must
  uphold; a future second implementation (e.g., email) must honor the same contract or
  risk breaking `AlertEvaluationService`'s assumption that notification calls are safe to
  make without their own try/except at the call site.

## Interview Talking Points

The interesting question isn't "which chat app" — it's "what does the delivery guarantee
need to be, given what's actually at stake." Here, the alert *record* is already durable
(Postgres, committed before notification) the moment `notify()` is called; the
notification is purely a courtesy on top of already-safe state. That's a fundamentally
different reliability requirement than the Agent's metrics push (ADR-002/ADR-011), where
the push *is* the only copy of the data until it's persisted. Recognizing that asymmetry
is what justifies fire-and-forget here while the Agent's transport layer retries and
buffers — the same "how much does losing this cost" question, answered differently
because the underlying risk is different. Revisit fire-and-forget only if notification
loss itself becomes an operational problem people actually hit (e.g., on-call missing a
critical page because Telegram happened to be down at that moment) — at that point a
durable notification queue is the right next step, not a Band-Aid retry loop bolted onto
the current synchronous call.
