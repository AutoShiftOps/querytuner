import logging

from app.llm.hf_client import call_hf, safe_parse_json
from app.utils.config import settings

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────


async def call_llm(
    prompt: str,
    provider: str | None = None,
    max_tokens: int = 600,
) -> dict:
    """
    Call the configured LLM provider.

    Returns:
        {
            "text":     str | None,    # LLM output
            "error":    str | None,    # User-friendly error message
            "provider": str,           # "huggingface" or "openai"
            "model":    str | None,    # Model used
        }
    """
    resolved_provider = provider or settings.default_llm_provider or "huggingface"

    if resolved_provider == "openai":
        return await _call_openai(prompt, max_tokens)
    else:
        return await _call_hf(prompt, max_tokens)


# ── HuggingFace ───────────────────────────────────────────────────────────────


async def _call_hf(prompt: str, max_tokens: int) -> dict:
    try:
        text = await call_hf(prompt, max_tokens=max_tokens)
        return {
            "text": text,
            "error": None,
            "provider": "huggingface",
            "model": settings.hf_model or "Qwen/Qwen2.5-Coder",
        }
    except RuntimeError as e:
        # RuntimeError = user-visible message already formatted in hf_client
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


async def _call_openai(prompt: str, max_tokens: int) -> dict:
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

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior database performance engineer. "
                        "Respond only with valid JSON as instructed. "
                        "No markdown fences, no extra text."
                    ),
                },
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


# ── JSON extraction helper (re-exported for use in agents) ───────────────────

__all__ = ["call_llm", "safe_parse_json"]
