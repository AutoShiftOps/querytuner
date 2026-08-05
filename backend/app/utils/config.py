"""
config.py — Centralized settings for QueryTuner
Issue #68: Add Supabase env vars

INSTRUCTIONS: Replace your existing backend/app/utils/config.py with this file.
All existing variables are preserved exactly. Only SUPABASE_URL and
SUPABASE_ANON_KEY are added at the bottom of the Settings class.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # -------------------------------------------------------------------------
    # AI providers — existing, unchanged
    # -------------------------------------------------------------------------
    hf_api_key: str = ""
    hf_model: str = "Qwen/Qwen2.5-Coder-3B-Instruct"
    hf_router_base_url: str = "https://router.huggingface.co"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    default_llm_provider: str = "huggingface"
    ai_max_tokens: int = 800
    max_query_chars: int = 32_000

    # -------------------------------------------------------------------------
    # Supabase — NEW (Issue #68)
    # Add these two lines to your .env and Render environment:
    #   SUPABASE_URL=https://xxxx.supabase.co
    #   SUPABASE_ANON_KEY=eyJ...
    # -------------------------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        # pydantic-settings defaults to extra="forbid" — any env var present
        # in .env / the process environment that isn't declared as a field
        # above crashes Settings() at import time, taking the whole app down
        # before it can even serve /health. Found this the hard way: env
        # vars added ahead of an unmerged branch (e.g. Phase 4's Clerk/
        # Stripe keys, added to Render in advance of that code landing) are
        # exactly this scenario on master today. Ignoring unknown vars is
        # the safe default for a service where env vars and deployed code
        # don't always change in lockstep.
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()
