-- Report page parity: persist detected security issues so shared report
-- pages can render the same Security Issues section as the main app.
-- Run after 004_ai_insights.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS security_issues JSONB NOT NULL DEFAULT '[]'::jsonb;
