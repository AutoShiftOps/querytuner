import asyncio
import os
from typing import Optional, Tuple


async def run_llm(provider: str, prompt: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns: (ai_insights, model_name, error)
    error is None when successful.
    """
    provider = (provider or "huggingface").lower().strip()

    if provider == "huggingface":
        model = os.getenv("HF_MODEL", "google/gemma-3-27b-it")  # set once
        if not os.getenv("HF_API_KEY", "").strip():
            return None, model, "HF_API_KEY not set on server"

        try:
            from app.llm.hf_client import HFLLM
            llm = HFLLM()
            text = await asyncio.wait_for(
                llm.chat([{"role": "user", "content": prompt}]),
                timeout=30.0)
        except Exception as e:
            return None, model, f"HuggingFace error: {e}"

        if not text or not str(text).strip():
            return None, model, "HuggingFace returned empty response"
        return text, model, None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        if not api_key:
            return None, model, "OPENAI_API_KEY not set on server"

        try:
            from openai import AsyncOpenAI
        except ImportError:
            return None, model, "openai package not installed on server"

        client = AsyncOpenAI(api_key=api_key)
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800,
                timeout=30.0,
            )
            text = response.choices[0].message.content
            if not text or not str(text).strip():
                return None, model, "OpenAI returned empty response"
            return text, model, None
        except Exception as e:
            return None, model, f"OpenAI API error: {e}"

    return None, None, f"Unknown provider: {provider}"
