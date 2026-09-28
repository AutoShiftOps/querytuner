-- Security audit follow-up (2026-09-28): confirm/enforce RLS instead of
-- trusting untracked dashboard state.
--
-- database.py's _supabase_headers() and backend/.env.example both claimed
-- "RLS is enabled on analyses and user_usage," but no migration file ever
-- ran ENABLE ROW LEVEL SECURITY or CREATE POLICY for any table, including
-- user_accounts (migration 007), which the comment didn't even mention —
-- that claim was unverifiable from the repo alone. Whoever owns the
-- Supabase project confirmed directly in the dashboard that a
-- dashboard-created "Enable read access for all users" policy existed on
-- analyses, granting the anon/authenticated roles unrestricted SELECT —
-- i.e. every analysis (any user's original_query, findings,
-- security_issues, ...) was readable by anyone holding the anon key, not
-- just the service_role-authenticated backend. That policy was found and
-- removed on 2026-09-28.
--
-- This migration does NOT add any new policies. The backend always
-- authenticates with the service_role key (see _supabase_headers()), which
-- bypasses RLS entirely regardless of what policies exist — that's the
-- intended access path for every read/write in database.py. With RLS
-- enabled and zero policies, these tables become deny-all for the anon and
-- authenticated roles (the only roles a leaked SUPABASE_ANON_KEY could ever
-- authenticate as) while staying fully functional for the backend. If a
-- policy is ever genuinely needed (e.g. a future direct-from-browser
-- Supabase read), add it deliberately in its own migration — not by
-- leaving RLS off or re-adding a blanket "allow all" policy.
--
-- Idempotent: ENABLE ROW LEVEL SECURITY is a no-op if already enabled;
-- DROP POLICY IF EXISTS is a no-op if the policy doesn't exist (or was
-- never named exactly this). Run after 009_sanitized_flag.sql.

ALTER TABLE public.analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Enable read access for all users" ON public.analyses;
