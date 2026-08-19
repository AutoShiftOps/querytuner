"""
Tests for /webhook/stripe in backend/app/main.py.

Regression coverage for a live 500 seen on every real Stripe delivery
(checkout.session.completed and customer.subscription.created both
failing): event["data"]["object"] is a stripe.StripeObject, not a plain
dict — it supports __getitem__ (event["type"] works) but not the dict
method .get(). StripeObject.__getattr__ falls through to self["get"] for
an unrecognized attribute name, which raises KeyError, re-raised as
AttributeError: get — uncaught, since it happens after the
construct_event() try/except, not inside it. Every data.get(...) call in
the handler crashed this way, for every real webhook delivery.

Reproduced locally before writing this test by sending a correctly-signed
synthetic event through the actual handler (same construct_event() call,
same signature-verification path) — confirmed both event types 500'd
pre-fix and confirmed the exact traceback above. Fixed by converting via
StripeObject's own .to_dict() immediately after extraction.
"""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app, settings

TEST_SECRET = "whsec_test_signing_secret"

client = TestClient(app)


def _sign(payload: bytes, secret: str) -> str:
    """Same construction Stripe itself uses: t=<unix ts>,v1=<hex hmac-sha256
    of '<ts>.<payload>'> — mirrors what stripe.Webhook.construct_event()
    verifies on the receiving end."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _post_event(event: dict, secret: str = TEST_SECRET):
    payload = json.dumps(event).encode()
    return client.post(
        "/webhook/stripe",
        content=payload,
        headers={"stripe-signature": _sign(payload, secret), "content-type": "application/json"},
    )


def _checkout_session_completed_event(*, user_id="user_test", customer_id="cus_test"):
    return {
        "id": "evt_test_checkout",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test",
                "object": "checkout.session",
                "client_reference_id": user_id,
                "customer": customer_id,
                "mode": "subscription",
                "payment_status": "paid",
                "status": "complete",
            }
        },
    }


def _subscription_created_event(*, customer_id="cus_test", status="active"):
    return {
        "id": "evt_test_subscription",
        "object": "event",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test",
                "object": "subscription",
                "customer": customer_id,
                "status": status,
            }
        },
    }


@pytest.fixture(autouse=True)
def _configured_webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", TEST_SECRET)


def test_checkout_session_completed_returns_200_not_500(monkeypatch):
    """The exact regression: this event type crashed every real delivery
    with an uncaught AttributeError before the fix."""
    calls = []

    async def fake_link_stripe_customer(user_id, stripe_customer_id):
        calls.append((user_id, stripe_customer_id))

    monkeypatch.setattr("app.main.link_stripe_customer", fake_link_stripe_customer)

    resp = _post_event(_checkout_session_completed_event(user_id="user_abc", customer_id="cus_abc"))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}
    assert len(calls) == 1
    assert calls[0][0] == "user_abc"
    assert calls[0][1] == "cus_abc"


def test_subscription_created_returns_200_not_500(monkeypatch):
    """Same crash, same fix, the other event type Stripe's dashboard showed
    failing."""
    calls = []

    async def fake_update_user_pro_status(stripe_customer_id, is_pro):
        calls.append((stripe_customer_id, is_pro))

    monkeypatch.setattr("app.main.update_user_pro_status", fake_update_user_pro_status)

    resp = _post_event(_subscription_created_event(customer_id="cus_xyz", status="active"))

    assert resp.status_code == 200, resp.text
    assert len(calls) == 1
    assert calls[0] == ("cus_xyz", True)


def test_checkout_session_missing_ids_logs_and_returns_200(monkeypatch):
    """Missing client_reference_id/customer is a real, expected case (the
    handler already logs and no-ops for it) — must stay a clean 200, not
    resurface as a crash now that .get() actually works."""
    calls = []

    async def fake_link_stripe_customer(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("app.main.link_stripe_customer", fake_link_stripe_customer)

    resp = _post_event(_checkout_session_completed_event(user_id=None, customer_id=None))
    assert resp.status_code == 200
    assert calls == []


def test_invalid_signature_returns_400_unaffected_by_fix():
    payload = json.dumps(_checkout_session_completed_event()).encode()
    resp = client.post(
        "/webhook/stripe",
        content=payload,
        headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_webhook_not_configured_returns_400(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    resp = _post_event(_checkout_session_completed_event())
    assert resp.status_code == 400
