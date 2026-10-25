import asyncio

import httpx
import pytest

from app.llm import hf_client
from app.utils.config import settings


class _Client:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        return self._handler(url, json)


def _patch(monkeypatch, handler):
    calls = []

    def wrapped(url, body):
        calls.append(body.get("model") or url)
        return handler(url, body)

    monkeypatch.setattr(hf_client.httpx, "AsyncClient", lambda timeout=None: _Client(wrapped))
    monkeypatch.setattr(settings, "hf_api_key", "hf_test")
    return calls


def test_out_of_credits_is_reported_once_not_retried(monkeypatch):
    calls = _patch(monkeypatch, lambda url, body: httpx.Response(402, content=b'{"error":"limit"}'))
    with pytest.raises(RuntimeError, match="credits are used up"):
        asyncio.run(hf_client.call_hf("P", max_tokens=100))
    assert len(calls) == 1


def test_every_model_failing_names_each_reason(monkeypatch):
    def handler(url, body):
        if "chat/completions" in url:
            if body["model"].endswith("7B-Instruct"):
                raise httpx.ReadTimeout("slow")
            return httpx.Response(400, content=b'{"error":"model not supported by provider"}')
        return httpx.Response(410, content=b"gone")

    _patch(monkeypatch, handler)
    with pytest.raises(RuntimeError) as e:
        asyncio.run(hf_client.call_hf("P", max_tokens=100))
    msg = str(e.value)
    assert "Qwen2.5-Coder-7B-Instruct: timed out" in msg and "HTTP 400" in msg and "legacy API" in msg


def test_max_tokens_capped_for_small_models(monkeypatch):
    seen = {}

    def handler(url, body):
        seen["max_tokens"] = body["max_tokens"]
        return httpx.Response(200, content=b'{"choices":[{"message":{"content":"{}"}}]}')

    _patch(monkeypatch, handler)
    asyncio.run(hf_client.call_hf("P", max_tokens=6000))
    assert seen["max_tokens"] == hf_client.HF_MAX_TOKENS
