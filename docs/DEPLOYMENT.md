# Deployment

This file is intentionally minimal — it points at the live configuration rather than
duplicating it, since a duplicated deployment doc is exactly the kind of thing that goes
stale (see `README.md`'s Architecture section for the high-level picture: frontend on
Vercel, backend on Render).

- **Backend (Render):** containerized via `backend/Dockerfile` (`python:3.11-slim`,
  `uvicorn`). Configure the environment variables listed in the README's "Environment
  Variables" table in the Render service's dashboard — there is no committed
  production `.env`.
- **Frontend (Vercel):** standard Vite build; set `VITE_API_URL` (and the optional
  `VITE_*` flags referenced in the README/LIMITATIONS, e.g. `VITE_PRO_CHECKOUT_ENABLED`,
  `VITE_STRIPE_PAYMENT_LINK`, `VITE_SENTRY_DSN`) in the Vercel project's environment
  variables.
- **CI:** see `.github/workflows/` — `backend-ci.yml` (pytest on every push),
  `main.yml`, and `keep-supabase-alive.yml` (pings Supabase every 3 days so the free
  tier doesn't pause after 7 days of inactivity).
- **Database:** Supabase, schema versioned under `backend/migrations/`.

For anything this file doesn't cover, the source of truth is the actual Render/Vercel
dashboard configuration, not a doc — ask whoever has access rather than assuming this
file is current.
