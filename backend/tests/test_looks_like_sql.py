import json

import pytest
from fastapi.testclient import TestClient

from app.main import app, rate_limit_store
from app.tools.query_parser import looks_like_sql
from app.utils import ai_cache

SAMPLES = json.loads(ai_cache.SAMPLES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s["sql"][:30])
def test_every_built_in_sample_is_sql(sample):
    assert looks_like_sql(sample["sql"])


@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "  (SELECT a FROM t) UNION (SELECT a FROM u)",
        "-- slow report\nSELECT * FROM t",
        "/* header */ WITH c AS (SELECT 1) SELECT * FROM c",
        "DECLARE @tmp TABLE (id nvarchar(20));\ninsert into @tmp select 1",
        "SET NOCOUNT ON;\nSELECT 1",
        "EXEC dbo.usp_report @id = 1",
        "UPDATE t SET a = 1 WHERE id = 2",
    ],
)
def test_real_sql_is_accepted(sql):
    assert looks_like_sql(sql)


@pytest.mark.parametrize(
    "text",
    ["hello world, please make my database fast", "why is my query slow?", "-- just a comment", "12345", ""],
)
def test_prose_and_junk_are_rejected(text):
    assert not looks_like_sql(text)


def test_mysql_hash_comment_before_sql():
    assert looks_like_sql("# nightly job\nSELECT 1", hash_comments=True)


def test_api_rejects_prose_with_a_clear_400():
    rate_limit_store.clear()
    resp = TestClient(app).post(
        "/analyze", json={"query": "hello world, please make my database fast", "db_type": "postgresql"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "not_sql"
    assert "doesn't look like a SQL query" in resp.json()["message"]
