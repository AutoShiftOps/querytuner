-- Report page parity: persist the plain-English Query Diagnosis text
-- (analyzer's plain_explanation) so shared report pages can render the
-- same QueryDiagnosis section as the main app.
-- Run after 002_phase2_schema_info.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS plain_explanation TEXT NULL;
