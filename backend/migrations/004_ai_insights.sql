-- Report page parity: persist AI Insights (structured JSON or prose text)
-- plus which provider/model produced it, so shared report pages can render
-- the same AI Insights panel as the main app.
-- ai_model already exists (001_initial_schema.sql) — only ai_insights and
-- ai_provider are new here.
-- Run after 003_plain_explanation.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS ai_insights TEXT NULL;

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS ai_provider TEXT NULL;
