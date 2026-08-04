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
    max_query_chars: int = 20_000

    # -------------------------------------------------------------------------
    # Supabase — NEW (Issue #68)
    # Add these two lines to your .env and Render environment:
    #   SUPABASE_URL=https://xxxx.supabase.co
    #   SUPABASE_ANON_KEY=eyJ...
    # -------------------------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # -------------------------------------------------------------------------
    # Clerk auth — Phase 4
    # clerk_publishable_key is the same value shipped to the frontend
    # (VITE_CLERK_PUBLISHABLE_KEY) — publishable keys are safe to hold
    # server-side too and are used to derive the Clerk JWKS URL for verifying
    # session tokens. clerk_secret_key is reserved for future use of Clerk's
    # backend API (e.g. fetching user profile data) — the JWT verification
    # in main.py only needs the publishable key.
    # -------------------------------------------------------------------------
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""

    # -------------------------------------------------------------------------
    # Stripe billing — Phase 4
    # -------------------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_price_id: str = ""
    stripe_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()
