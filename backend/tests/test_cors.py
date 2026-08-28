"""
Tests for backend/app/main.py's CORS configuration —
docs/querytuner-cors-fix.md.

Pins the real allowlist down (settings.frontend_url + localhost:3000)
so this can't silently regress back to the dev-mode `allow_origins=["*"]`
leftover the DZone-launch-readiness audit flagged.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.utils.config import settings

client = TestClient(app)


def test_cors_rejects_arbitrary_origin():
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


def test_cors_allows_configured_frontend_origin():
    resp = client.get(
        "/usage",
        headers={
            "Origin": settings.frontend_url,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == settings.frontend_url


def test_cors_allows_localhost_dev_server():
    """localhost:3000 is always allowed regardless of FRONTEND_URL, so
    local dev against a deployed backend works without setting it."""
    resp = client.get(
        "/usage",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_allows_www_subdomain_regression():
    """Hotfix regression test: querytuner.com 307-redirects to
    www.querytuner.com at the DNS/Vercel level (confirmed live via curl),
    so the browser's real Origin header on every API call from the
    deployed site is "https://www.querytuner.com" — not the bare domain
    settings.frontend_url defaults to. The original CORS-allowlist fix
    only allowed the bare domain, silently CORS-blocking every real
    visitor on /capabilities, /usage, and /analyze itself (the request
    succeeded server-side; the browser just refused to let the frontend
    read the response). Both must be explicitly allowed."""
    resp = client.get(
        "/usage",
        headers={
            "Origin": "https://www.querytuner.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "https://www.querytuner.com"


def test_cors_allows_bare_domain_even_when_frontend_url_differs():
    """https://querytuner.com (bare, no www) is explicitly allowed
    regardless of what FRONTEND_URL is actually set to — a direct API
    call from that origin (not through the browser's page-navigation
    redirect, which doesn't apply to XHR/fetch Origin headers) must not
    depend on FRONTEND_URL happening to match it."""
    resp = client.get(
        "/usage",
        headers={
            "Origin": "https://querytuner.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "https://querytuner.com"
