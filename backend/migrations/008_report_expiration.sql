-- Phase 5 quick win #116: URL expiration and deletion for shareable reports.
--
-- Why: GET /report/{analysis_id} returned any analysis by UUID, forever, to
-- anyone with the link — no auth check, no expiration. A permanent,
-- unauthenticated, un-revocable link to someone's query (which may embed
-- table/column names, sometimes literal WHERE-clause values) sitting in a
-- Slack thread or ticket forever is a data-retention gap.
--
-- Run after 007_user_accounts_table.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;

-- Nullable and deliberately NOT backfilled for existing rows: this
-- migration doesn't retroactively expire anything already shared. Only
-- analyses created after the application code picks this column up
-- (backend/app/utils/database.py's save_analysis(), which sets it to
-- created_at + a fixed window — see ANALYSIS_EXPIRATION_DAYS) get an
-- expiration going forward. A row with expires_at IS NULL never expires.
--
-- No new index: the read path (get_analysis()) only ever compares one
-- already-fetched row's own expires_at against now() — it doesn't filter
-- a list of rows by expiration, so there's nothing here for an index to
-- speed up. If a future batch-cleanup job starts querying "all rows past
-- their expiry", that job is the point to add
-- idx_analyses_expires_at, not this migration.
