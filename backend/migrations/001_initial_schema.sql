-- Phase 1.5: Initial analyses table
-- Created: May 2025
-- Run in Supabase SQL Editor
-- Idempotent: safe to re-run

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.analyses (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  query_hash       TEXT        NOT NULL,
  db_type          TEXT        NOT NULL,
  original_query   TEXT        NOT NULL,
  findings         JSONB       NOT NULL DEFAULT '[]'::jsonb,
  severity         TEXT        NOT NULL DEFAULT 'low'::text,
  optimized_query  TEXT        NULL,
  readability_score DOUBLE PRECISION NULL,
  analysis_time_ms DOUBLE PRECISION NULL,
  used_ai          BOOLEAN     NULL DEFAULT false,
  ai_model         TEXT        NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT analyses_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_query_hash
  ON public.analyses USING btree (query_hash);

CREATE INDEX IF NOT EXISTS idx_analyses_created_at
  ON public.analyses USING btree (created_at DESC);
