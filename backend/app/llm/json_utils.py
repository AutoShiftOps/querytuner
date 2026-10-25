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
