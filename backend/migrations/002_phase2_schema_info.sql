-- Phase 2: add schema_info column
-- Run after 001_initial_schema.sql

ALTER TABLE public.analyses
ADD COLUMN IF NOT EXISTS schema_info TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_analyses_has_schema
  ON public.analyses ((schema_info IS NOT NULL));
