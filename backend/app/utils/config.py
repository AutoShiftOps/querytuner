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
    # 800 was too tight for structured JSON responses on verbose queries
    # (long rewritten_query + multiple findings) — the model would get cut
    # off mid-generation, producing invalid JSON that the frontend could
    # only render as raw text. See sql_analyzer.py's _try_llm for the fix
    # that actually wires this value through to the LLM call.
    ai_max_tokens: int = 1500
    # Pro-tier / absolute ceiling. See free_tier_max_query_chars below for
    # the smaller limit applied to free and anonymous users.
    max_query_chars: int = 32_000
    # Phase 4: free/anonymous users get a smaller per-query character limit
    # than Pro — this doubles as an upgrade prompt (main.py's /analyze
    # returns upgrade_available: true when this is what rejected the
    # query), not just an anti-abuse measure.
    free_tier_max_query_chars: int = 8_000

    # -------------------------------------------------------------------------
    # Supabase — NEW (Issue #68)
    # Add these lines to your .env and Render environment:
    #   SUPABASE_URL=https://xxxx.supabase.co
    #   SUPABASE_ANON_KEY=eyJ...
    #   SUPABASE_SERVICE_ROLE_KEY=eyJ...
    #
    # supabase_service_role_key is what the backend actually authenticates
    # every analyses/user_usage read+write with (see database.py's
    # _supabase_headers()) — RLS is enabled on both tables now, and
    # service_role is the only key that bypasses it without needing custom
    # policies. NEVER send this key to the frontend/browser; it grants
    # unrestricted read/write on every RLS-protected table in the project,
    # unlike the anon key. supabase_anon_key is kept only because it's a
    # harmless, already-public value (Supabase's own docs call it safe to
    # ship client-side) — nothing in this codebase currently uses it for
    # anything, since the frontend never talks to Supabase directly (the
    # shareable report page goes through GET /report/{id} on this backend).
    # -------------------------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

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
