# Migrations

Run these in Supabase SQL Editor in order.
All files are idempotent — safe to re-run.

| File | Phase | Description |
|---|---|---|
| 001_initial_schema.sql | 1.5 | analyses table + query_hash and created_at indexes |
| 002_phase2_schema_info.sql | 2 | schema_info column for schema-aware analysis |
| 003_plain_explanation.sql | Phase 2 polish | add plain_explanation column for Query Diagnosis on report page |
| 004_ai_insights.sql | Phase 2 polish | add ai_insights and ai_provider columns for AI Insights on report page |
| 005_security_issues.sql | Phase 2 polish | add security_issues column for Security Issues section on report page |
| 006_user_accounts.sql | 4 | user_id column on analyses + user_usage table (monthly analysis count, is_pro, stripe_customer_id) for Clerk auth + Stripe billing |
| 007_user_accounts_table.sql | 4 | user_accounts table (is_pro, stripe_customer_id — one row per user, not per user per month) + backfill from user_usage; fixes Pro status silently lapsing every calendar month. Non-destructive: user_usage keeps its (now vestigial) is_pro/stripe_customer_id columns for now |
| 008_report_expiration.sql | 5 | analyses.expires_at (nullable, not backfilled) — shareable report links now expire (default 90 days, set at write time) and a signed-in owner can revoke their own link early via DELETE /report/{id} (soft-delete: sets expires_at to now()) |
| 009_sanitized_flag.sql | 5 | analyses.was_sanitized (NOT NULL, default false) + (user_id, was_sanitized) index — self-reported flag from QueryRequest, backs #124's History-page sanitized indicator and sanitized-only filter |

## Disaster recovery
1. Create a new Supabase project
2. Run each migration file in order in the SQL Editor
3. Update SUPABASE_URL and SUPABASE_ANON_KEY in Render environment
4. Redeploy backend on Render — data layer is restored
