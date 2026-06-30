"""
conftest.py — pytest path bootstrap + shared fixtures
Place at: backend/conftest.py (same level as app/ and tests/, NOT inside tests/)

WHY THIS FILE EXISTS — two separate problems it solves:

1. PATH RESOLUTION
   test_heuristics.py does:      from app.agents.sql_analyzer import ...
   test_sql_analyzer.py does:    from backend.app.tools... import ...  (now fixed to app.tools)
   Both assume different working directories. This file guarantees `app.*`
   resolves correctly no matter where pytest is invoked from.

2. SHARED FIXTURES
   test_sql_analyzer.py (in tests/tools/) referenced an `analyzer` fixture
   that was only ever defined in test_heuristics.py (in tests/). Pytest
   fixtures defined in a test file are NOT automatically visible to other
   test files — only fixtures in conftest.py are shared project-wide.
   Defining `analyzer` here once means EVERY test file, in any subfolder
   under tests/, can use it without redefining or importing anything.
"""

import sys
from pathlib import Path

import pytest

# ── Path bootstrap ────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Shared fixtures ────────────────────────────────────────────────────────────

from app.agents.sql_analyzer import SQLAnalyzerAgent  # noqa: E402


@pytest.fixture(scope="module")
def analyzer():
    """
    Shared SQLAnalyzerAgent instance for any test file under tests/.
    Module-scoped — one instance per test module, not per test, for speed.
    """
    return SQLAnalyzerAgent()
