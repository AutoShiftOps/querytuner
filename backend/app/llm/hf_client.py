import os
from typing import Dict, List, Optional

import httpx


class HFLLM:
    """
    Hugging Face Router (OpenAI-compatible) chat completions client.

    Calls: POST https://router.huggingface.co/v1/chat/completions
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or os.getenv("HF_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("HF_API_KEY is missing")

        self.model = (model or os.getenv("HF_MODEL", "google/gemma-3-27b-it")).strip()
        self.max_tokens_cap = int(os.getenv("AI_MAX_TOKENS", "300"))
        self.base_url = os.getenv("HF_ROUTER_BASE_URL", "https://router.huggingface.co").rstrip("/")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 700,
        temperature: float = 0.2,
        timeout_s: float = 30.0,
    ) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        max_tokens = min(int(max_tokens), self.max_tokens_cap)  # clamp
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, headers=headers, json=payload)

        if r.status_code >= 400:
            # Important: surface real HF error to your UI
            raise RuntimeError(f"HF router error {r.status_code}: {r.text}")

        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError(f"Unexpected HF response shape: {data}")
