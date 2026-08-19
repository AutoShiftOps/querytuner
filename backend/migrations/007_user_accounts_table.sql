-- Phase 4 follow-up: split subscription state (is_pro, stripe_customer_id)
-- out of user_usage into a dedicated per-user table.
--
-- Root cause this fixes: user_usage is keyed by UNIQUE(user_id, month) —
-- one row per user per calendar month. is_pro/stripe_customer_id were
-- living on that same month-scoped row, written once at checkout by
-- link_stripe_customer() and flipped by update_user_pro_status(). Neither
-- field ever carried forward to a new month's row (created fresh by
-- increment_user_usage() the first time a user analyzes something in a new
-- month), so a real subscriber's is_pro silently reverted to false the
-- first time they used the app in a new calendar month — while their
-- Stripe subscription (and Stripe's own billing) kept working exactly as
-- expected. Confirmed by reading get_user_stripe_customer_id's docstring
-- and update_user_pro_status() in backend/app/utils/database.py: is_pro is
-- only ever set on a row that already carries a matching
-- stripe_customer_id, and analysis_count's monthly rows never carry one.
--
-- Run after 006_user_accounts.sql

CREATE TABLE IF NOT EXISTS public.user_accounts (
  user_id            TEXT        PRIMARY KEY,
  is_pro             BOOLEAN     NOT NULL DEFAULT false,
  stripe_customer_id TEXT        NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Same reason the equivalent index on user_usage exists (migration 006):
-- looked up by the Stripe webhook (customer.subscription.*), which only
-- carries the Stripe customer_id, never the Clerk user_id.
CREATE INDEX IF NOT EXISTS idx_user_accounts_stripe_customer_id
  ON public.user_accounts USING btree (stripe_customer_id);

-- Backfill: one user_accounts row per user_id that currently has is_pro=true
-- or a non-null stripe_customer_id on ANY user_usage row, so no existing
-- Pro (or previously-Pro) user's linkage is lost by this migration.
--
-- DISTINCT ON (user_id) ... ORDER BY user_id, updated_at DESC picks the
-- single most-recently-updated qualifying row per user — which is also the
-- most accurate one to trust: is_pro can only ever be true on a row that
-- already carries a matching stripe_customer_id (update_user_pro_status()
-- only PATCHes rows filtered by an existing stripe_customer_id), so a
-- churned user's latest row correctly backfills is_pro=false while still
-- preserving their stripe_customer_id for reference — that's the accurate
-- current state, not a stale earlier "was Pro" snapshot.
--
-- ON CONFLICT (user_id) DO NOTHING makes this safe to re-run.
INSERT INTO public.user_accounts (user_id, is_pro, stripe_customer_id)
SELECT DISTINCT ON (user_id)
  user_id,
  is_pro,
  stripe_customer_id
FROM public.user_usage
WHERE is_pro = true OR stripe_customer_id IS NOT NULL
ORDER BY user_id, updated_at DESC
ON CONFLICT (user_id) DO NOTHING;

-- Deliberately NOT dropping is_pro/stripe_customer_id from user_usage here.
-- Both columns become vestigial as of this migration (the application code
-- reads/writes user_accounts instead — see backend/app/utils/database.py),
-- but leaving them in place keeps this migration non-destructive and lets
-- the new path be proven in production before a follow-up migration drops
-- them.
