"""
Tests for backend/app/utils/database.py's Supabase upsert helpers.

Covers two related but separate concerns:

1. The on_conflict gap found via live Render logs (increment_user_usage()
   and, before migration 007, link_stripe_customer() too): a POST with
   `Prefer: resolution=merge-duplicates` but no `on_conflict` naming the
   unique constraint silently falls through to a plain INSERT, which 409s
   on every call after the first for the same key. See this repo's git
   history for the original live repro against Supabase.

2. The Pro-status-lapses-monthly bug (migration 007): is_pro and
   stripe_customer_id used to live on user_usage, keyed by
   UNIQUE(user_id, month) — a fresh month meant a fresh row that carried
   neither field forward, so a real subscriber's is_pro silently reverted
   to false the first time they used the app in a new calendar month.
   Fixed by moving both fields onto a dedicated per-user user_accounts
   table (migration 007_user_accounts_table.sql) that isn't re-created
   every month. test_is_pro_survives_a_new_months_user_usage_row below is
   the direct regression test for this.

The fake transport below simulates BOTH tables closely enough to catch
real PostgREST behavior: user_usage (analysis_count, keyed by
(user_id, month), needs on_conflict=user_id,month to upsert) and
user_accounts (is_pro/stripe_customer_id, keyed by user_id alone, needs
on_conflict=user_id to upsert) — a POST without the right on_conflict
against an existing key 409s on either table, exactly like the real
service does.
"""

import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.utils import database as database_module


class FakeSupabase:
    """In-memory stand-in for the two Supabase tables database.py talks to
    for usage/billing state: user_usage (monthly analysis_count) and
    user_accounts (per-user is_pro/stripe_customer_id, migration 007)."""

    def __init__(self):
        self.usage_rows: dict[tuple[str, str], dict] = {}  # (user_id, month) -> row
        self.account_rows: dict[str, dict] = {}  # user_id -> row
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/rest/v1/user_usage":
            return self._handle_user_usage(request)
        if request.url.path == "/rest/v1/user_accounts":
            return self._handle_user_accounts(request)
        raise AssertionError(f"unexpected path {request.url.path}")

    def _handle_user_usage(self, request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())

        if request.method == "GET":
            user_id = query.get("user_id", [""])[0].removeprefix("eq.")
            month = query.get("month", [""])[0].removeprefix("eq.")
            row = self.usage_rows.get((user_id, month))
            return httpx.Response(200, json=[row] if row else [])

        if request.method == "POST":
            body = json.loads(request.content)
            key = (body["user_id"], body["month"])
            prefer = request.headers.get("prefer", "")
            is_merge_upsert = "resolution=merge-duplicates" in prefer and "on_conflict" in query
            if key in self.usage_rows and not is_merge_upsert:
                return httpx.Response(
                    409,
                    json={
                        "code": "23505",
                        "message": ("duplicate key value violates unique constraint " '"user_usage_user_month_unique"'),
                    },
                )
            merged = {**self.usage_rows.get(key, {}), **body}
            self.usage_rows[key] = merged
            return httpx.Response(201, json=[merged])

        raise AssertionError(f"unexpected {request.method} on user_usage")

    def _handle_user_accounts(self, request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())

        if request.method == "GET":
            user_id = query.get("user_id", [""])[0].removeprefix("eq.")
            row = self.account_rows.get(user_id)
            return httpx.Response(200, json=[row] if row else [])

        if request.method == "POST":
            body = json.loads(request.content)
            key = body["user_id"]
            prefer = request.headers.get("prefer", "")
            is_merge_upsert = "resolution=merge-duplicates" in prefer and "on_conflict" in query
            if key in self.account_rows and not is_merge_upsert:
                return httpx.Response(
                    409,
                    json={
                        "code": "23505",
                        "message": 'duplicate key value violates unique constraint "user_accounts_pkey"',
                    },
                )
            merged = {**self.account_rows.get(key, {}), **body}
            self.account_rows[key] = merged
            return httpx.Response(201, json=[merged])

        if request.method == "PATCH":
            customer_id = query.get("stripe_customer_id", [""])[0].removeprefix("eq.")
            body = json.loads(request.content)
            updated = []
            for row in self.account_rows.values():
                if row.get("stripe_customer_id") == customer_id:
                    row.update(body)
                    updated.append(row)
            return httpx.Response(200, json=updated)

        raise AssertionError(f"unexpected {request.method} on user_accounts")


@pytest.fixture
def fake_supabase(monkeypatch):
    """Points database.py's Supabase calls at the fake tables above instead
    of the network, and satisfies _supabase_configured() with dummy
    (non-real) credentials so this test never depends on the real .env."""
    fake = FakeSupabase()
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
    post_requests = [r for r in fake_supabase.requests if r.method == "POST" and r.url.path == "/rest/v1/user_usage"]
    assert len(post_requests) == 1
    query = parse_qs(post_requests[0].url.query.decode())
    assert query.get("on_conflict") == ["user_id,month"]


@pytest.mark.asyncio
async def test_link_stripe_customer_twice_merges_not_409s(fake_supabase):
    """link_stripe_customer upserts into user_accounts by user_id (its
    primary key, migration 007) — a user who upgrades, cancels, and
    re-subscribes must not 409 on the second link. Also confirms the
    on_conflict=user_id parameter is actually necessary here: the fake's
    _handle_user_accounts POST path 409s a second insert without it, same
    mechanism as the user_usage on_conflict bug this session already found
    once — worth proving this new call site doesn't repeat it."""
    user_id = "user_stripe_regression"

    await database_module.link_stripe_customer(user_id, "cus_first")
    await database_module.link_stripe_customer(user_id, "cus_second")

    row = fake_supabase.account_rows[user_id]
    assert row["stripe_customer_id"] == "cus_second"


@pytest.mark.asyncio
async def test_link_stripe_customer_sends_on_conflict_user_id(fake_supabase):
    await database_module.link_stripe_customer("user_x", "cus_x")
    post_requests = [r for r in fake_supabase.requests if r.method == "POST" and r.url.path == "/rest/v1/user_accounts"]
    assert len(post_requests) == 1
    query = parse_qs(post_requests[0].url.query.decode())
    assert query.get("on_conflict") == ["user_id"]


@pytest.mark.asyncio
async def test_update_user_pro_status_patches_user_accounts(fake_supabase):
    """update_user_pro_status PATCHes user_accounts by stripe_customer_id —
    it never inserts, so it isn't exposed to the on_conflict gap."""
    user_id = "user_pro_status_test"
    await database_module.link_stripe_customer(user_id, "cus_pro_test")

    await database_module.update_user_pro_status("cus_pro_test", True)

    result = await database_module.get_user_usage(user_id, "2026-08")
    assert result["is_pro"] is True


@pytest.mark.asyncio
async def test_is_pro_survives_a_new_months_user_usage_row(fake_supabase):
    """THE regression test for the bug this migration fixes. Before
    migration 007, is_pro lived on the monthly user_usage row — a fresh
    month's row (created by increment_user_usage the first time a user
    analyzes something in a new calendar month) never carried is_pro
    forward, so a real subscriber's Pro status silently reverted to False
    the moment the calendar rolled over, even though nothing about their
    actual Stripe subscription changed.

    Simulates: user goes Pro in month 1 (checkout webhook: link + status
    update), then the calendar rolls to month 2 and they run their first
    analysis of the new month (creating a fresh user_usage row for month 2,
    exactly as increment_user_usage/the /analyze flow would). is_pro must
    still read True in month 2 — sourced from user_accounts, which has
    exactly one row per user and was never touched by the month-2 row
    being created.
    """
    user_id = "user_month_rollover_test"

    # Month 1: real subscription flow (checkout webhook equivalents).
    await database_module.link_stripe_customer(user_id, "cus_rollover_test")
    await database_module.update_user_pro_status("cus_rollover_test", True)
    await database_module.increment_user_usage(user_id, "2026-08")
    assert (await database_module.get_user_usage(user_id, "2026-08"))["is_pro"] is True

    # Month 2 rolls over: first analysis of the new month creates a brand
    # new user_usage row — this is exactly the step that used to reset
    # is_pro to False before migration 007.
    await database_module.increment_user_usage(user_id, "2026-09")
    month_2_usage = await database_module.get_user_usage(user_id, "2026-09")

    assert month_2_usage["is_pro"] is True, "is_pro must survive a new month's user_usage row"
    assert month_2_usage["count"] == 1  # the month-2 row's own count, independent of is_pro
    # Confirm user_accounts really does have exactly one row for this user
    # (not one per month) — the structural reason this now works.
    assert user_id in fake_supabase.account_rows
    assert fake_supabase.account_rows[user_id]["is_pro"] is True


@pytest.mark.asyncio
async def test_get_user_stripe_customer_id_direct_lookup(fake_supabase):
    """Migration 007: a direct lookup on user_accounts by user_id (its
    primary key) — no more searching across a user's monthly user_usage
    rows for the most recent non-null value the way the pre-migration
    workaround had to."""
    user_id = "user_lookup_test"
    await database_module.link_stripe_customer(user_id, "cus_lookup_test")

    result = await database_module.get_user_stripe_customer_id(user_id)

    assert result == "cus_lookup_test"
    get_requests = [r for r in fake_supabase.requests if r.method == "GET" and r.url.path == "/rest/v1/user_accounts"]
    assert len(get_requests) == 1
    query = parse_qs(get_requests[0].url.query.decode())
    assert query["user_id"] == [f"eq.{user_id}"]
    assert "month" not in query


@pytest.mark.asyncio
async def test_get_user_stripe_customer_id_none_when_never_subscribed(fake_supabase):
    result = await database_module.get_user_stripe_customer_id("user_never_subscribed")
    assert result is None
