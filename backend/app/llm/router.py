import logging

import httpx

from app.llm.hf_client import call_hf, safe_parse_json
from app.llm.prompts import REWRITE_GUARDRAILS
from app.utils.config import settings

# Issue #74: inject dialect-specific context into LLM system prompts
from app.utils.dialect_config import get_llm_context

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────


async def call_llm(
    prompt: str,
    provider: str | None = None,
    max_tokens: int = 600,
    db_type: str = "postgresql",  # Issue #74: added db_type parameter
) -> dict:
    """
    Call the configured LLM provider.

    Args:
        prompt:    The user/task prompt.
        provider:  "huggingface" | "openai" | "anthropic" | None (uses default from config).
        max_tokens: Max tokens to generate.
        db_type:   Database dialect — injects dialect-specific context into
                   the system prompt so the model never hallucinates wrong syntax.

    Returns:
        {
            "text":     str | None,
            "error":    str | None,
            "provider": str,
            "model":    str | None,
        }
    """
    resolved_provider = provider or settings.default_llm_provider or "huggingface"

    if resolved_provider == "openai":
        return await _call_openai(prompt, max_tokens, db_type)
    if resolved_provider == "anthropic":
        return await _call_anthropic(prompt, max_tokens, db_type)
    else:
        return await _call_hf(prompt, max_tokens, db_type)


# ── HuggingFace ───────────────────────────────────────────────────────────────


async def _call_hf(prompt: str, max_tokens: int, db_type: str) -> dict:
    """
    Issue #74: db_type is passed to call_hf so the dialect context
    can be injected into the instruct prompt in hf_client.py.
    """
    try:
        text = await call_hf(prompt, max_tokens=max_tokens, db_type=db_type)
        return {
            "text": text,
            "error": None,
            "provider": "huggingface",
            "model": settings.hf_model or "Qwen/Qwen2.5-Coder",
        }
    except RuntimeError as e:
        logger.warning("HF LLM failed: %s", e)
        return {
            "text": None,
            "error": str(e),
            "provider": "huggingface",
            "model": None,
        }
    except Exception as e:
        logger.error("HF LLM unexpected error: %s", e, exc_info=True)
        return {
            "text": None,
            "error": "AI model unavailable — heuristic analysis is complete above.",
            "provider": "huggingface",
            "model": None,
        }


# ── OpenAI ────────────────────────────────────────────────────────────────────


async def _call_openai(prompt: str, max_tokens: int, db_type: str) -> dict:
    if not settings.openai_api_key:
        return {
            "text": None,
            "error": "OpenAI API key not configured on this server.",
            "provider": "openai",
            "model": None,
        }

    try:
        import openai  # lazy import — openai package optional

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        model = settings.openai_model or "gpt-4o-mini"

        system_content = _system_prompt(db_type)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.1,
        )

        text = response.choices[0].message.content
        if text is not None:
            text = text.strip()

        return {
            "text": text,
            "error": None,
            "provider": "openai",
            "model": model,
        }

    except Exception as e:
        logger.error("OpenAI LLM error: %s", e, exc_info=True)
        return {
            "text": None,
            "error": "OpenAI request failed — check API key and quota.",
            "provider": "openai",
            "model": None,
        }


def _system_prompt(db_type: str) -> str:
    # Issue #74: dialect-specific system prompt instead of a generic one
    return (
        f"{get_llm_context(db_type)}\n\n"
        "Respond only with valid JSON as instructed. "
        "No markdown fences, no extra text outside the JSON. "
        "Use exactly these JSON keys: most_impactful_improvements, "
        "recommended_indexes, rewritten_query, targeted_fixes, risky_assumptions. "
        "No other top-level keys. "
        f"{REWRITE_GUARDRAILS}"
    )


# ── Anthropic (Claude) ───────────────────────────────────────────────────────

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


async def _call_anthropic(prompt: str, max_tokens: int, db_type: str) -> dict:
    """
    Messages API over plain httpx (no SDK dependency). No temperature/top_p:
    current Claude models reject sampling parameters with a 400.
    """
    model = settings.anthropic_model or "claude-haiku-5-5"
    if not settings.anthropic_api_key:
        return {
            "text": None,
            "error": "Anthropic API key not configured on this server.",
            "provider": "anthropic",
            "model": None,
        }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                ANTHROPIC_MESSAGES_URL,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": _system_prompt(db_type),
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            logger.error("Anthropic LLM error %s: %s", resp.status_code, resp.text[:500])
            return {
                "text": None,
                "error": "Anthropic request failed — check API key, model name and quota.",
                "provider": "anthropic",
                "model": model,
            }
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        if data.get("stop_reason") == "max_tokens":
            logger.warning("Anthropic reply hit max_tokens (%s)", max_tokens)
        return {"text": text or None, "error": None, "provider": "anthropic", "model": data.get("model") or model}
    except Exception as e:
        logger.error("Anthropic LLM error: %s", e, exc_info=True)
        return {
            "text": None,
            "error": "Anthropic request failed — check API key and quota.",
            "provider": "anthropic",
            "model": model,
        }


# ── JSON extraction helper ────────────────────────────────────────────────────

__all__ = ["call_llm", "safe_parse_json"]
