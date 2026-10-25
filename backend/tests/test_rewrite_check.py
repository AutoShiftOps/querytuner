import json

from app.llm.rewrite_check import check_rewrite, check_targeted_fixes, review_ai_output, wants_targeted_fixes

ORIGINAL = """select * from (
select [Order #]=SH.No_
,[Last Scan Location] = OD.LastScanHub
,[Item Scan Status] = (CASE WHEN SS.ScannedItems = 0 THEN 'No Items Scan' ELSE 'Partial' END)
,[PickupHub]= (select top 1 [PickupHub] from @Data where [OrderNo] = SH.No_)
from [dbo].[Sales Header] SH with(nolock)
inner join [dbo].[Metro_OrderData] OD with(nolock) on SH.No_ = OD.OrderNo
LEFT JOIN #ScanSummary SS ON SS.[Sales Order No] = SH.No_
where SH.[Order Status]=10000 --and SL.[CSR Assign To] in ('RETURNS')
)ilv"""


def test_rewrite_that_drops_a_join_and_column_is_rejected():
    # What gpt-4o-mini returned in the report: [Item Scan Status] and the
    # #ScanSummary join are gone, and a stray comma is left behind.
    bad = ORIGINAL.replace(
        ",[Item Scan Status] = (CASE WHEN SS.ScannedItems = 0 THEN 'No Items Scan' ELSE 'Partial' END)\n", ""
    ).replace("LEFT JOIN #ScanSummary SS ON SS.[Sales Order No] = SH.No_\n", "")
    assert "drops table" in check_rewrite(ORIGINAL, bad)
    stray = ORIGINAL.replace("= OD.LastScanHub", "= OD.LastScanHub,")
    assert "stray comma" in check_rewrite(ORIGINAL, stray)
    no_col = ORIGINAL.replace(",[Item Scan Status] = (CASE", ",(CASE")
    assert "drops output column" in check_rewrite(ORIGINAL, no_col)


def test_rewrite_that_keeps_everything_passes():
    good = ORIGINAL.replace("select top 1 [PickupHub]", "SELECT TOP (1) [PickupHub]").replace("--and SL.", "")
    assert check_rewrite(ORIGINAL, good) is None
    assert check_rewrite("SELECT a AS x, b FROM t", "WITH c AS (SELECT a, b FROM t) SELECT a AS x, b FROM c") is None


def test_targeted_fix_kept_only_when_before_text_is_in_query():
    fixes = [
        {
            "title": "ok",
            "before": "select top 1 [PickupHub] from @Data",
            "after": "select top (1) [PickupHub] from @Data",
        },
        {"title": "made up", "before": "SELECT foo FROM bar", "after": "SELECT foo FROM baz"},
        {"title": "no-op", "before": "SH.No_ = OD.OrderNo", "after": "SH.No_ = OD.OrderNo"},
        {"title": "breaks parens", "before": "(CASE WHEN", "after": "CASE WHEN"},
    ]
    kept, dropped = check_targeted_fixes(ORIGINAL, fixes)
    assert [f["title"] for f in kept] == ["ok"] and dropped == 3


def test_review_removes_rejected_rewrite_and_records_why():
    reply = json.dumps({"recommended_indexes": [], "rewritten_query": "SELECT 1 FROM [dbo].[Sales Header] SH,"})
    out = json.loads(review_ai_output(ORIGINAL, reply))
    assert out["rewritten_query"] == "" and out["rewrite_rejected"]
    assert review_ai_output(ORIGINAL, '{"rewritten_query": "SELECT ISNULL(') == '{"rewritten_query": "SELECT ISNULL('


def test_targeted_mode_for_batches_and_long_queries_only():
    assert wants_targeted_fixes("DECLARE @t TABLE (id int)\nselect * from @t")
    assert wants_targeted_fixes("SELECT 1; SELECT 2;")
    assert wants_targeted_fixes("SELECT a FROM t WHERE b = 1 " + "AND c = 2 " * 400)
    assert not wants_targeted_fixes("WITH c AS (SELECT a FROM t)\nSELECT a FROM c\nUNION ALL\nSELECT a FROM u")
    assert not wants_targeted_fixes("SELECT 'a;b' FROM t -- DECLARE x\n")
