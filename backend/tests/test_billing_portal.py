"""
Tests for POST /billing-portal in backend/app/main.py — creates a Stripe
Billing Portal session so a Pro user can manage their subscription without
any custom billing UI in this app.

Covers: auth required (no useful anonymous path here), the no-customer-id
edge case returning a clear 400 instead of a raw Stripe API error, the
success path returning {"url": ...}, and a Stripe-side failure surfacing as
a 502 rather than an unhandled exception. stripe.billing_portal.Session.create
is monkeypatched — these tests never call the real Stripe API.
"""

from fastapi.testclient import TestClient

from app.main import app, get_current_user

client = TestClient(app)


def test_requires_sign_in(monkeypatch):
    resp = client.post("/billing-portal")
    assert resp.status_code == 401


def test_no_stripe_customer_id_returns_clear_400(monkeypatch):
    async def fake_get_customer_id(user_id):
        return None

    monkeypatch.setattr("app.main.get_user_stripe_customer_id", fake_get_customer_id)
    app.dependency_overrides[get_current_user] = lambda: "user_never_subscribed"
    try:
        resp = client.post("/billing-portal")
        assert resp.status_code == 400
        assert "subscription" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_success_returns_portal_url(monkeypatch):
    async def fake_get_customer_id(user_id):
        assert user_id == "user_pro_test"
        return "cus_test_123"

    captured = {}

    class _FakeSession:
        url = "https://billing.stripe.com/session/test_abc"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr("app.main.get_user_stripe_customer_id", fake_get_customer_id)
    monkeypatch.setattr("app.main.stripe.billing_portal.Session.create", fake_create)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.post("/billing-portal")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"url": "https://billing.stripe.com/session/test_abc"}
        assert captured["customer"] == "cus_test_123"
        assert captured["return_url"]  # exact value is settings.frontend_url, just needs to be present
    finally:
        app.dependency_overrides.clear()


def test_stripe_api_failure_returns_502_not_raw_error(monkeypatch):
    async def fake_get_customer_id(user_id):
        return "cus_test_123"

    def fake_create(**kwargs):
        raise RuntimeError("stripe.error.APIConnectionError: could not connect")

    monkeypatch.setattr("app.main.get_user_stripe_customer_id", fake_get_customer_id)
    monkeypatch.setattr("app.main.stripe.billing_portal.Session.create", fake_create)
    app.dependency_overrides[get_current_user] = lambda: "user_pro_test"
    try:
        resp = client.post("/billing-portal")
        assert resp.status_code == 502
    finally:
        app.dependency_overrides.clear()


# get_user_stripe_customer_id()'s own behavior (now a direct lookup on
# user_accounts, migration 007 — see that migration and
# link_stripe_customer's docstring for why) is covered in
# tests/test_database.py, alongside the rest of that migration's tests.
# The tests above mock it entirely, so they're unaffected by that change.
