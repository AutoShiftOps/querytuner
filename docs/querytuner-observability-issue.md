# Phase 5 — Observability (#135)

**Status:** Partially shipped. Error tracking and correlation IDs are real,
tested code, live the moment `SENTRY_DSN` is set. Uptime monitoring and
alerting are **not code problems** — they're third-party account setup this
doc walks through, not something a repo change can complete on its own.

## What the issue asks for

> No production observability currently exists — no error tracking (e.g.
> Sentry), no uptime monitoring, and no alerting on failures or degraded
> performance. This is a blocker for enterprise reliability expectations.
>
> Scope:
> - Integrate error tracking/APM (e.g. Sentry) for backend and frontend
> - Add uptime monitoring (e.g. UptimeRobot, Better Uptime, or Grafana Cloud) for critical endpoints
> - Configure alerting (email/Slack/PagerDuty) for error-rate spikes, downtime, and latency SLO breaches
> - Add structured logging with correlation IDs for request tracing

## What shipped (this pass)

- **Backend error tracking** (`app/main.py`): `sentry-sdk[fastapi]` initialized
  from `SENTRY_DSN` — same degrades-gracefully pattern as every other optional
  key in this codebase (`HF_API_KEY`, `OPENAI_API_KEY`, the Stripe keys):
  blank env var, zero behavior change, confirmed by the full existing test
  suite running with it unset. `send_default_pii=False` — this app already
  goes out of its way client-side (the query sanitizer) to keep real schema
  names off the backend; Sentry's default PII capture would undo that.
  `traces_sample_rate=0.1` — light APM sampling, not full tracing, to stay
  inside a free-tier Sentry project's event quota.
- **Correlation IDs** (`app/main.py`'s `request_id_middleware`): every
  response carries an `X-Request-ID` header — reuses one supplied by the
  caller (or an upstream proxy) if present, otherwise mints a UUID4. Tagged
  onto the active Sentry scope so an error event and the request that
  caused it share the same ID across logs and Sentry. Placed outermost in
  the middleware stack (added after the existing rate-limiter) so even a
  429 short-circuited by rate limiting still carries the header.
- **DB-aware health check** (`app/utils/database.py`'s
  `check_database_health()`, wired into `GET /health`): a lightweight
  `GET .../rest/v1/analyses?limit=1` against Supabase, 3s timeout, never
  raises. `/health` still returns `200`/`"healthy"` even when this fails —
  the heuristic engine works with Supabase fully down (every call in
  `database.py` already has its own try/except fallback) — but now exposes
  `checks.database: "ok" | "unreachable"` so a human (or a smarter monitor
  reading the body, not just the status code) can see persistence-layer
  degradation without it paging as a full outage.
- **9 new tests** (`tests/test_observability.py`): `/health`'s two states,
  request-ID generation/echo/uniqueness, and `check_database_health()`
  against a mocked Supabase (200 / error status / network failure / not
  configured). Full suite: 331 passed (up from 322), 1 pre-existing xfail.
- **Frontend error tracking** (`frontend/src/main.jsx`): `@sentry/react`
  initialized from `VITE_SENTRY_DSN`, same no-op-when-blank pattern.

## What's genuinely not a code change

**Uptime monitoring** and **alerting** are external services by definition —
there's no repo change that "adds" a third party watching your server from
outside it. Setup, once you have the accounts:

1. **Sentry** (error tracking + alerting) — sentry.io, free tier:
   - Create two projects: one Python/FastAPI, one React.
   - Copy each DSN into `SENTRY_DSN` (Render, backend) and
     `VITE_SENTRY_DSN` (Vercel, frontend).
   - Alerts → Create Alert Rule → "when the number of events in an issue is
     more than N in 1 hour" → notify via email or a Slack integration.
     Sentry's Slack integration (Settings → Integrations → Slack) is the
     lowest-friction path to the issue's "Slack" alerting ask.
2. **Uptime monitor** — UptimeRobot (free tier, 50 monitors) or Better
   Uptime:
   - New monitor → HTTPS → `https://api.querytuner.com/health` → check
     every 5 minutes → alert contacts (email, and Slack via UptimeRobot's
     own Slack integration).
   - This is exactly why `/health` reports `checks.database` in its body
     now rather than just a bare `200` — once you're looking at this in a
     monitor's dashboard, the degraded-vs-fully-down distinction is visible
     without digging into Sentry.
3. **Latency SLO breaches** (the issue's third alerting bullet) — Sentry's
   free-tier performance monitoring (from `traces_sample_rate=0.1` above)
   surfaces p95 transaction duration per endpoint; an alert rule can fire
   on that directly. A dedicated latency SLO dashboard (Grafana Cloud, per
   the issue's own suggestion) is a heavier lift than either of the above
   and is left as further backlog, not attempted in this pass.

None of this needs another repo change to *start* working — it needs an
account and five minutes in each service's UI, using the env vars and
endpoint this pass already added.
