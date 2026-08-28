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
