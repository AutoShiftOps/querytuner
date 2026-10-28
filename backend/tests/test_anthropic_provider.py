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
    assert out["text"] is None and "Anthropic request failed (HTTP 401" in out["error"]


def test_anthropic_error_names_the_cause(monkeypatch):
    body = {"type": "error", "error": {"type": "not_found_error", "message": "model: claude-nope"}}
    _patch(monkeypatch, httpx.Response(404, content=json.dumps(body).encode()))
    out = asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=10))
    assert "not a valid model ID" in out["error"] and "model: claude-nope" in out["error"]
    assert "test-key" not in out["error"]


def test_anthropic_without_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    out = asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=10))
    assert out["text"] is None and "not configured" in out["error"]


class _SeqClient:
    def __init__(self, responses, bodies):
        self._responses = list(responses)
        self._bodies = bodies

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self._bodies.append(json)
        return self._responses.pop(0)


def _patch_seq(monkeypatch, responses, model="claude-haiku-5-5"):
    bodies: list = []
    monkeypatch.setattr(router.httpx, "AsyncClient", lambda timeout=None: _SeqClient(responses, bodies))
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "anthropic_model", model)
    return bodies


def _ok(text='{"a": 1}', stop="end_turn"):
    reply = {"model": "m", "stop_reason": stop, "content": [{"type": "text", "text": text}] if text else []}
    return httpx.Response(200, content=json.dumps(reply).encode())


def test_thinking_settings_per_model(monkeypatch):
    for model, thinking in [
        ("claude-haiku-5-5", {"type": "disabled"}),
        ("claude-sonnet-5-5", {"type": "between_tools"}),
        ("claude-opus-5-5", None),
    ]:
        bodies = _patch_seq(monkeypatch, [_ok()], model=model)
        asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=100))
        assert bodies[0]["output_config"] == {"effort": "low"}
        assert bodies[0].get("thinking") == thinking


def test_rejected_thinking_settings_retry_without_them(monkeypatch):
    bad = httpx.Response(400, content=b'{"type":"error","error":{"type":"invalid_request_error","message":"effort"}}')
    bodies = _patch_seq(monkeypatch, [bad, _ok()])
    out = asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=100))
    assert out["text"] == '{"a": 1}'
    assert "thinking" in bodies[0] and "thinking" not in bodies[1] and "output_config" not in bodies[1]


def test_budget_spent_thinking_gives_a_clear_error(monkeypatch):
    _patch_seq(monkeypatch, [_ok(text="", stop="max_tokens")])
    out = asyncio.run(router.call_llm("P", provider="anthropic", max_tokens=6000))
    assert out["text"] is None and "output budget thinking" in out["error"]
