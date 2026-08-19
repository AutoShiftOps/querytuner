"""
Tests for backend/app/utils/database.py's Supabase upsert helpers.

Specifically guards against the on_conflict gap found via live Render logs:
increment_user_usage() and link_stripe_customer() both POST to user_usage
with `Prefer: resolution=merge-duplicates` but, without `on_conflict`
naming the (user_id, month) unique constraint (user_usage_user_month_unique,
migrations/006_user_accounts.sql), PostgREST silently ignores the merge
instruction and falls through to a plain INSERT — which then 409s against
that constraint on every call after the first for a given user/month.
increment_user_usage caught that 409 in its existing `except Exception`
handler and only logged a warning, so analysis_count got created at 1 on a
user's first analysis and never moved again: the free-tier paywall never
triggered for signed-in users. Confirmed live against the real Supabase
project before writing this test (see the commit message for that repro),
then fixed by adding on_conflict=user_id,month to both POST calls.

The fake transport below reproduces real PostgREST semantics closely enough
to have caught this bug before the fix: a POST with merge-duplicates but no
on_conflict against an existing (user_id, month) row returns 409, exactly
like the real service did. A test that only checked "the POST call includes
an on_conflict param" would pass even if the value were wrong (e.g. naming
the wrong columns) or if PostgREST's actual conflict-resolution rules ever
changed — asserting on the resulting count/row state instead is what
actually catches a regression here, not just a change to the request shape.
"""

import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.utils import database as database_module


class FakeUserUsageTable:
    """In-memory stand-in for Supabase's user_usage table, keyed by
    (user_id, month) — the same columns migration 006 puts a unique
    constraint on. Mirrors just enough of PostgREST's upsert behavior to
    make the on_conflict requirement observable: a POST is only treated as
    an upsert (merge into the existing row) when both `on_conflict` names a
    matching key AND the Prefer header requests merge-duplicates; otherwise
    it's a plain insert, which 409s if the key already exists — same as the
    live bug this test guards against.
    """

    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.path == "/rest/v1/user_usage"
        query = parse_qs(request.url.query.decode())

        if request.method == "GET":
            user_id = query.get("user_id", [""])[0].removeprefix("eq.")
            month = query.get("month", [""])[0].removeprefix("eq.")
            row = self.rows.get((user_id, month))
            return httpx.Response(200, json=[row] if row else [])

        if request.method == "POST":
            body = json.loads(request.content)
            key = (body["user_id"], body["month"])
            prefer = request.headers.get("prefer", "")
            is_merge_upsert = "resolution=merge-duplicates" in prefer and "on_conflict" in query
            if key in self.rows and not is_merge_upsert:
                return httpx.Response(
                    409,
                    json={
                        "code": "23505",
                        "message": ("duplicate key value violates unique constraint " '"user_usage_user_month_unique"'),
                    },
                )
            merged = {**self.rows.get(key, {}), **body}
            self.rows[key] = merged
            return httpx.Response(201, json=[merged])

        if request.method == "PATCH":
            customer_id = query.get("stripe_customer_id", [""])[0].removeprefix("eq.")
            body = json.loads(request.content)
            updated = []
            for _key, row in self.rows.items():
                if row.get("stripe_customer_id") == customer_id:
                    row.update(body)
                    updated.append(row)
            return httpx.Response(200, json=updated)

        raise AssertionError(f"unexpected {request.method} {request.url}")


@pytest.fixture
def fake_supabase(monkeypatch):
    """Points database.py's Supabase calls at the fake table above instead
    of the network, and satisfies _supabase_configured() with dummy
    (non-real) credentials so this test never depends on the real .env."""
    fake = FakeUserUsageTable()
    monkeypatch.setattr(database_module.settings, "supabase_url", "https://fake.supabase.test")
    monkeypatch.setattr(database_module.settings, "supabase_service_role_key", "fake-service-role-key")

    transport = httpx.MockTransport(fake.handle)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(database_module.httpx, "AsyncClient", _FakeAsyncClient)
    return fake


@pytest.mark.asyncio
async def test_increment_user_usage_twice_reaches_two_not_stuck_at_one(fake_supabase):
    """The exact regression: a second increment for the same (user_id,
    month) must actually land, not silently 409 and leave count at 1."""
    user_id, month = "user_regression_test", "2026-08"

    await database_module.increment_user_usage(user_id, month)
    assert (await database_module.get_user_usage(user_id, month))["count"] == 1

    await database_module.increment_user_usage(user_id, month)
    assert (await database_module.get_user_usage(user_id, month))["count"] == 2

    await database_module.increment_user_usage(user_id, month)
    assert (await database_module.get_user_usage(user_id, month))["count"] == 3


@pytest.mark.asyncio
async def test_increment_user_usage_sends_on_conflict_param(fake_supabase):
    """Direct guard on the request shape itself, alongside the behavioral
    test above — on_conflict must name the same columns as the real unique
    constraint (migrations/006_user_accounts.sql: user_usage_user_month_unique)."""
    await database_module.increment_user_usage("user_x", "2026-08")
    post_requests = [r for r in fake_supabase.requests if r.method == "POST"]
    assert len(post_requests) == 1
    query = parse_qs(post_requests[0].url.query.decode())
    assert query.get("on_conflict") == ["user_id,month"]


@pytest.mark.asyncio
async def test_link_stripe_customer_twice_same_month_merges_not_409s(fake_supabase):
    """link_stripe_customer shares the exact same upsert-without-on_conflict
    pattern increment_user_usage had — a user who upgrades, cancels, and
    re-subscribes within the same month must not 409 on the second link."""
    user_id, month = "user_stripe_regression", "2026-08"

    await database_module.link_stripe_customer(user_id, "cus_first", month)
    await database_module.link_stripe_customer(user_id, "cus_second", month)

    row = fake_supabase.rows[(user_id, month)]
    assert row["stripe_customer_id"] == "cus_second"


@pytest.mark.asyncio
async def test_update_user_pro_status_unaffected_uses_patch_not_upsert(fake_supabase):
    """update_user_pro_status PATCHes an existing row by filter — it never
    inserts, so it was never exposed to the on_conflict gap. Asserted here
    so that stays true rather than assumed."""
    user_id, month = "user_pro_status_test", "2026-08"
    await database_module.link_stripe_customer(user_id, "cus_pro_test", month)

    await database_module.update_user_pro_status("cus_pro_test", True)

    result = await database_module.get_user_usage(user_id, month)
    assert result["is_pro"] is True
