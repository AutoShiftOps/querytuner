# Migrations

Run these in Supabase SQL Editor in order.
All files are idempotent — safe to re-run.

| File | Phase | Description |
|---|---|---|
| 001_initial_schema.sql | 1.5 | analyses table + query_hash and created_at indexes |
| 002_phase2_schema_info.sql | 2 | schema_info column for schema-aware analysis |
| 003_plain_explanation.sql | — | plain_explanation column so report pages can render Query Diagnosis |
| 004_ai_insights.sql | — | ai_insights and ai_provider columns so report pages can render AI Insights (ai_model already existed) |

## Disaster recovery
1. Create a new Supabase project
2. Run each migration file in order in the SQL Editor
3. Update SUPABASE_URL and SUPABASE_ANON_KEY in Render environment
4. Redeploy backend on Render — data layer is restored
