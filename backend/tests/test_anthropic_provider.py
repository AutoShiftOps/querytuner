import asyncio
import json

import httpx

from app.llm import router
from app.utils.config import settings


class _FakeClient:
    def __init__(self, response, seen):
        self._response = response
        self._seen = seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self._seen.update(url=url, headers=headers, body=json)
        return self._response


def _patch(monkeypatch, response):
    seen: dict = {}
    monkeypatch.setattr(router.httpx, "AsyncClient", lambda timeout=None: _FakeClient(response, seen))
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "anthropic_model", "claude-haiku-5-5")
    return seen


def test_anthropic_call_shape_and_text(monkeypatch):
    reply = {"model": "claude-haiku-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": '{"a": 1}'}]}
    seen = _patch(monkeypatch, httpx.Response(200, content=json.dumps(reply).encode()))
    out = asyncio.run(router.call_llm("PROMPT", provider="anthropic", max_tokens=1234, db_type="sqlserver"))
    assert out == {"text": '{"a": 1}', "error": None, "provider": "anthropic", "model": "claude-haiku-5-5"}
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "test-key" and seen["headers"]["anthropic-version"]
    body = seen["body"]
    assert body["max_tokens"] == 1234 and body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert "SQL Server" in body["system"] or "sqlserver" in body["system"].lower()
    assert "temperature" not in body  # current Claude models reject sampling params


def test_anthropic_error_status_is_reported_not_raised(monkeypatch):
    _patch(monkeypatch, httpx.Response(401, content=b'{"error": "bad key"}'))
    out = asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=10))
    assert out["text"] is None and "Anthropic request failed" in out["error"]


def test_anthropic_without_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    out = asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=10))
    assert out["text"] is None and "not configured" in out["error"]
