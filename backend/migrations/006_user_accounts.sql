-- Phase 4: user accounts — Clerk user_id on analyses, plus a per-user
-- monthly usage/Pro-status table backing the free-tier limit and Stripe
-- subscription status.
-- Run after 005_security_issues.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS user_id TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_analyses_user_id
  ON public.analyses USING btree (user_id);

CREATE TABLE IF NOT EXISTS public.user_usage (
  id                 UUID        NOT NULL DEFAULT gen_random_uuid(),
  user_id            TEXT        NOT NULL,
  month              TEXT        NOT NULL, -- 'YYYY-MM', UTC
  analysis_count     INTEGER     NOT NULL DEFAULT 0,
  is_pro             BOOLEAN     NOT NULL DEFAULT false,
  stripe_customer_id TEXT        NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT user_usage_pkey PRIMARY KEY (id),
  CONSTRAINT user_usage_user_month_unique UNIQUE (user_id, month)
);

CREATE INDEX IF NOT EXISTS idx_user_usage_user_id
  ON public.user_usage USING btree (user_id);

-- Looked up by the Stripe webhook (customer.subscription.*) to find which
-- user_usage row to flip is_pro on.
CREATE INDEX IF NOT EXISTS idx_user_usage_stripe_customer_id
  ON public.user_usage USING btree (stripe_customer_id);
