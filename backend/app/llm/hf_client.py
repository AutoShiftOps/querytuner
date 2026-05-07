import json
import logging
import re

import httpx

from app.utils.config import settings

logger = logging.getLogger(__name__)

# ── Model priority list ───────────────────────────────────────────────────────
# Router tries these in order — first one that returns 200 is used.
# Qwen2.5-Coder stays as primary; fallbacks added for resilience.
ROUTER_MODELS = [
    "Qwen/Qwen2.5-Coder-7B-Instruct",  # larger, more likely on serverless fleet
    "Qwen/Qwen2.5-Coder-3B-Instruct",  # original — may not be on router
    "mistralai/Mistral-7B-Instruct-v0.3",  # reliable fallback
    "HuggingFaceH4/zephyr-7b-beta",  # last resort
]

ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
LEGACY_URL = "https://api-inference.huggingface.co/models/{model}"

# ── Public entry point ────────────────────────────────────────────────────────


async def call_hf(prompt: str, max_tokens: int = 600) -> str:
    """
    Call HuggingFace LLM. Returns the model's text response.
    Raises RuntimeError with a user-friendly message on failure.
    """
    token = settings.hf_api_key
    if not token:
        raise RuntimeError("HF_API_KEY is not configured on the server.")

    # Try router first (faster, supports chat format)
    for model in ROUTER_MODELS:
        try:
            text = await _call_router(prompt, model, token, max_tokens)
            logger.info("HF router success: model=%s", model)
            return text
        except _RouterError as e:
            logger.warning("HF router failed for %s: %s — trying next", model, e)
            continue
        except Exception as e:
            logger.warning("HF router unexpected error for %s: %s", model, e)
            continue

    # All router models failed — fall back to legacy inference API
    logger.info("All router models failed, falling back to legacy inference API")
    primary_model = settings.hf_model or ROUTER_MODELS[1]
    return await _call_legacy(prompt, primary_model, token, max_tokens)


# ── Router implementation ─────────────────────────────────────────────────────


class _RouterError(Exception):
    pass


async def _call_router(
    prompt: str,
    model: str,
    token: str,
    max_tokens: int,
) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # OpenAI-compatible format — use max_tokens NOT max_new_tokens
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior database performance engineer. "
                    "Respond only with valid JSON as instructed. "
                    "No markdown fences, no explanatory text outside the JSON."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": max_tokens,  # OpenAI format — NOT max_new_tokens
        "temperature": 0.1,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(ROUTER_URL, headers=headers, json=payload)

    if resp.status_code in (400, 404, 422):
        # Model not available or bad request — try next model
        raise _RouterError(f"HTTP {resp.status_code}: {resp.text[:120]}")

    if resp.status_code == 401:
        raise RuntimeError("HuggingFace API key is invalid or expired.")

    if resp.status_code == 429:
        raise RuntimeError("HuggingFace rate limit hit. Try again in a moment.")

    if not resp.is_success:
        raise _RouterError(f"HTTP {resp.status_code}")

    data = resp.json()

    # Standard OpenAI response shape
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise _RouterError(f"Unexpected router response shape: {e} — {str(data)[:120]}") from e


# ── Legacy inference API fallback ─────────────────────────────────────────────


async def _call_legacy(
    prompt: str,
    model: str,
    token: str,
    max_tokens: int,
) -> str:
    """
    Fall back to the standard HF inference endpoint.
    This uses the text-generation task format (not chat completions).
    """
    url = LEGACY_URL.format(model=model)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # HF native format — uses max_new_tokens, not max_tokens
    payload = {
        "inputs": _build_instruct_prompt(prompt),
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": 0.1,
            "return_full_text": False,  # don't echo the prompt
            "do_sample": True,
        },
    }

    async with httpx.AsyncClient(timeout=35.0) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code == 503:
        # Model is loading — this is the HF "cold start"
        raise RuntimeError("HuggingFace model is loading (free tier cold start). " "Please try again in 20–30 seconds.")

    if not resp.is_success:
        raise RuntimeError(
            f"HuggingFace inference API returned {resp.status_code}. " f"Check HF_API_KEY and model availability."
        )

    data = resp.json()

    # Legacy API returns list of generated_text dicts
    if isinstance(data, list) and data:
        text = data[0].get("generated_text", "")
    elif isinstance(data, dict):
        text = data.get("generated_text", "")
    else:
        raise RuntimeError(f"Unexpected legacy API response: {str(data)[:120]}")

    if not text:
        raise RuntimeError("LLM returned empty response")

    return text.strip()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_instruct_prompt(user_prompt: str) -> str:
    """
    Wrap prompt in Mistral/Qwen instruct format for the legacy endpoint.
    Both Qwen2.5-Coder and Mistral use [INST]...[/INST] delimiters.
    """
    system = (
        "You are a senior database performance engineer. "
        "Respond only with valid JSON as instructed. "
        "No markdown fences, no extra text."
    )
    return f"<s>[INST] {system}\n\n{user_prompt} [/INST]"


def safe_parse_json(raw: str) -> dict | None:
    """
    Parse JSON from LLM output robustly.
    Handles: markdown fences, leading/trailing text, partial echo.
    """
    if not raw:
        return None

    # Strip markdown code fences
    clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()

    # Try direct parse first
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Find the first {...} block
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from LLM output: %s", raw[:200])
    return None
