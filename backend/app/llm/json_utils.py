"""JSON extraction from LLM replies (shared by every provider)."""

import json
import logging
import re

logger = logging.getLogger(__name__)


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


def repair_truncated_json(text: str) -> str:
    """
    Close an unterminated string and any open arrays/objects so JSON that was
    cut off mid-reply (token limit) parses. Never invents data, only closes
    what the model had opened. Mirrors the frontend's repairTruncatedJson.
    """
    return _repair(text)[0]


def _repair(text: str) -> tuple[str, bool]:
    """(repaired JSON, last top-level value was complete when the text stopped)."""
    stack: list[str] = []
    in_string = escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    repaired = text + ('"' if in_string else "")
    dangling_key = False
    # Cut off inside an object key ({"a": 1, "targ): drop the dangling key.
    if stack and stack[-1] == "{":
        trimmed = re.sub(r'(?:,\s*|(?<=\{)\s*)"(?:[^"\\]|\\.)*"\s*$', "", repaired)
        dangling_key = trimmed != repaired
        repaired = trimmed
    repaired = re.sub(r",\s*$", "", repaired)
    repaired = re.sub(r":\s*$", ": null", repaired)
    # Back at the root object, between members: whatever came before is whole.
    last_complete = len(stack) == 1 and (not in_string or dangling_key)
    return repaired + "".join("}" if c == "{" else "]" for c in reversed(stack)), last_complete


def parse_json_lenient(raw: str) -> tuple[dict | None, bool, bool]:
    """
    (data, was_truncated, last_value_complete). Falls back to repairing a
    reply that was cut off; last_value_complete says whether the value that
    was being written when it stopped is whole (False means drop or distrust it).
    """
    data = safe_parse_json(raw) if raw else None
    if isinstance(data, dict):
        return data, False, True
    if not raw:
        return None, False, True
    clean = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    start = clean.find("{")
    if start == -1:
        return None, False, True
    repaired, last_complete = _repair(clean[start:])
    try:
        data = json.loads(repaired)
    except json.JSONDecodeError:
        return None, False, True
    return (data, True, last_complete) if isinstance(data, dict) else (None, False, True)
