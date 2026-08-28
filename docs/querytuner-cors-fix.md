# CORS hardening — `allow_origins=["*"]` → real allowlist

**Why:** flagged in `docs/querytuner-dzone-launch-readiness.md` ahead of the Aug 31 DZone article — `backend/app/main.py`'s own comment (`# Update for production`) marks this as a known dev-mode leftover, sitting exactly where a technical reader would look first. Small, self-contained fix — safe to ship independently of the Clerk/Stripe production switch.

## The fix

`backend/app/main.py`, current code:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Replace with:
```python
app.add_middleware(
    CORSMiddleware,
    # Real allowlist, not "*" — settings.frontend_url already exists
    # (used by the Stripe Billing Portal return_url) and already defaults
    # to production while being overridable via FRONTEND_URL for local
    # dev, so reusing it here needs no new env var. localhost:3000 is
    # additionally always allowed (matches frontend/vite.config.js's dev
    # server port) so local development against a deployed backend still
    # works without setting FRONTEND_URL.
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**One thing to double-check before merging, since I can't see the Vercel project config from here:** if this repo relies on Vercel's per-branch preview deployments (each getting its own `*.vercel.app` URL) being able to call the real API during testing, a strict allowlist will break those previews' API calls. If that's not a workflow you actually use, ignore this — the fix above is correct as-is. If you do use preview deployments against the real backend, the fix should either add a wildcard-subdomain match for your Vercel project (Starlette's `CORSMiddleware` supports `allow_origin_regex` for exactly this) or those previews should point at a separate staging backend instead. Flagging as a judgment call rather than guessing at your actual workflow.

## Test to add

`backend/tests/test_main.py` (or a new small `test_cors.py`, matching whichever convention the repo prefers) — pin the allowlist down so this can't silently regress back to `"*"`:

```python
def test_cors_rejects_arbitrary_origin(client):
    resp = client.get(
        "/usage",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette's CORSMiddleware simply omits the ACAO header for a
    # disallowed origin rather than erroring — assert its absence, not a
    # specific status code.
    assert "access-control-allow-origin" not in resp.headers


def test_cors_allows_configured_frontend_origin(client):
    resp = client.get(
        "/usage",
        headers={
            "Origin": settings.frontend_url,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == settings.frontend_url
```

(Adjust the endpoint used if `/usage` needs auth in a way that complicates the test fixture — any unauthenticated-reachable route works fine here since this is testing the CORS layer, not the endpoint's own logic. `settings` is importable from `app.utils.config` — already imported elsewhere in `test_main.py`'s neighborhood if not in this exact file yet.)

## Verification before merge

Same as every PR this session: run the full backend suite (currently 308 passing + 1 xfail) to confirm nothing else assumed the wildcard, `ruff check .`, and manually confirm in a browser devtools Network tab (or via `curl -H "Origin: https://querytuner.com" -I https://api.querytuner.com/usage`) that the real frontend origin still gets `access-control-allow-origin` back correctly against the deployed backend once this ships.
