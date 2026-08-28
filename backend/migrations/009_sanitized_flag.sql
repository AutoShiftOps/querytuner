-- Issue #124: sanitized/unsanitized indicator + filter on the report
-- management dashboard (History page).
--
-- Why: the client-side query sanitizer (table/column names replaced with
-- dummy values before ever leaving the browser) has always been
-- browser-only — the substitution map is never sent to the server, by
-- design. That means the backend has never had any way to know whether a
-- given saved analysis came from a sanitized query or not, which is
-- exactly the property #124 asks the History list to show and filter by.
-- Confirmed via grep before writing this migration: no "sanitiz" string
-- anywhere in migrations/ or app/ prior to this.
--
-- Run after 008_report_expiration.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS was_sanitized BOOLEAN NOT NULL DEFAULT false;

-- Defaults to false for existing rows — none of them carried this signal
-- before now, and "not sanitized" is the safe, honest default rather than
-- guessing. Only analyses created after the application code picks this
-- column up (backend/app/utils/database.py's save_analysis(), populated
-- from QueryRequest.was_sanitized — a self-reported flag from the
-- client's own sanitizer state) get a real value going forward.
--
-- Indexed: unlike expires_at (migration 008, only ever compared on one
-- already-fetched row), this column IS filtered across a list —
-- GET /history's new sanitized-only view — so a supporting index is
-- worth adding now rather than after that query shows up slow.
CREATE INDEX IF NOT EXISTS idx_analyses_user_sanitized
  ON public.analyses USING btree (user_id, was_sanitized);
