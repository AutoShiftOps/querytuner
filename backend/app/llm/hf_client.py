import json
import logging
import re

import httpx

from app.utils.config import settings

# Issue #74: inject dialect-specific context into HF system prompts
from app.utils.dialect_config import get_llm_context

logger = logging.getLogger(__name__)

ROUTER_MODELS = [
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "Qwen/Qwen2.5-Coder-3B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "HuggingFaceH4/zephyr-7b-beta",
]

ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
LEGACY_URL = "https://api-inference.huggingface.co/models/{model}"


# ── Public entry point ───────────────────────────────────────────────────────


async def call_hf(
    prompt: str,
    max_tokens: int = 600,
    db_type: str = "postgresql",  # Issue #74: dialect context injected below
) -> str:
    """
    Call HuggingFace LLM. Returns the model's text response.
    Raises RuntimeError with a user-friendly message on failure.
    """
    token = settings.hf_api_key
    if not token:
        raise RuntimeError("HF_API_KEY is not configured on the server.")

    for model in ROUTER_MODELS:
        try:
            text = await _call_router(prompt, model, token, max_tokens, db_type)
            logger.info("HF router success: model=%s dialect=%s", model, db_type)
            return text
        except _RouterError as e:
            logger.warning("HF router failed for %s: %s — trying next", model, e)
            continue
        except Exception as e:
            logger.warning("HF router unexpected error for %s: %s", model, e)
            continue

    logger.info("All router models failed, falling back to legacy inference API")
    primary_model = settings.hf_model or ROUTER_MODELS[1]
    return await _call_legacy(prompt, primary_model, token, max_tokens, db_type)


# ── Router implementation ────────────────────────────────────────────────────


class _RouterError(Exception):
    pass


async def _call_router(
    prompt: str,
    model: str,
    token: str,
    max_tokens: int,
    db_type: str,  # Issue #74
) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Issue #74: dialect-specific system message replaces the generic one.
    # get_llm_context() returns e.g. "You are analyzing a PostgreSQL query.
    # Reference VACUUM ANALYZE, CONCURRENTLY index creation..." etc.
    dialect_system = (
        f"{get_llm_context(db_type)}\n\n"
        "Respond only with valid JSON as instructed. "
        "No markdown fences, no explanatory text outside the JSON. "
        "Use exactly these JSON keys: most_impactful_improvements, "
        "recommended_indexes, rewritten_query, risky_assumptions. "
        "No other top-level keys."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": dialect_system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(ROUTER_URL, headers=headers, json=payload)

    if resp.status_code in (400, 404, 422):
        raise _RouterError(f"HTTP {resp.status_code}: {resp.text[:120]}")

    if resp.status_code == 401:
        raise RuntimeError("HuggingFace API key is invalid or expired.")

    if resp.status_code == 429:
        raise RuntimeError("HuggingFace rate limit hit. Try again in a moment.")

    if not resp.is_success:
        raise _RouterError(f"HTTP {resp.status_code}")

    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise _RouterError(f"Unexpected router response shape: {e} — {str(data)[:120]}") from e


# ── Legacy inference API fallback ────────────────────────────────────────────


async def _call_legacy(
    prompt: str,
    model: str,
    token: str,
    max_tokens: int,
    db_type: str,  # Issue #74
) -> str:
    url = LEGACY_URL.format(model=model)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "inputs": _build_instruct_prompt(prompt, db_type),  # Issue #74: pass db_type
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": 0.1,
            "return_full_text": False,
            "do_sample": True,
        },
    }

    async with httpx.AsyncClient(timeout=35.0) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code == 503:
        raise RuntimeError("HuggingFace model is loading (free tier cold start). " "Please try again in 20–30 seconds.")

    if not resp.is_success:
        raise RuntimeError(
            f"HuggingFace inference API returned {resp.status_code}. " "Check HF_API_KEY and model availability."
        )

    data = resp.json()

    if isinstance(data, list) and data:
        text = data[0].get("generated_text", "")
    elif isinstance(data, dict):
        text = data.get("generated_text", "")
    else:
        raise RuntimeError(f"Unexpected legacy API response: {str(data)[:120]}")

    if not text:
        raise RuntimeError("LLM returned empty response")

    return text.strip()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_instruct_prompt(user_prompt: str, db_type: str = "postgresql") -> str:
    """
    Wrap prompt in Mistral/Qwen instruct format for the legacy endpoint.
    Issue #74: uses dialect-specific system context instead of generic string.
    """
    # Issue #74: dialect context tells the model which DB it's working with
    system = (
        f"{get_llm_context(db_type)} "
        "Respond only with valid JSON as instructed. "
        "No markdown fences, no extra text. "
        "Use exactly these JSON keys: most_impactful_improvements, "
        "recommended_indexes, rewritten_query, risky_assumptions. "
        "No other top-level keys."
    )
    return f"<s>[INST] {system}\n\n{user_prompt} [/INST]"


def safe_parse_json(raw: str) -> dict | None:
    """
    Parse JSON from LLM output robustly.
    Handles: markdown fences, leading/trailing text, partial echo.
    """
    if not raw:
        return None

    clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from LLM output: %s", raw[:200])
    return None
