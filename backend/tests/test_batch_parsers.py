"""
Tests for backend/app/tools/batch_parsers.py — Issue #120.

Per the design doc's item 3 (normalized-text caveat), also confirms the
existing heuristic engine's column/predicate extraction against the
parameterized placeholder syntax pg_stat_statements/performance_schema
actually hand back ($1, ?) — a real correctness risk the doc flags
explicitly, not something to just assume works.
"""

import json

from app.tools.batch_parsers import (
    parse_performance_schema,
    parse_pg_stat_statements,
    parse_query_store,
    rank_top_n,
)
from app.tools.index_recommender import IndexRecommender
from app.tools.query_parser import QueryParser


class TestPgStatStatements:
    def test_json_array_with_pg13_column_names(self):
        raw = json.dumps(
            [
                {
                    "query": "SELECT * FROM orders WHERE status = $1",
                    "calls": 120,
                    "total_exec_time": 4521.33,
                    "mean_exec_time": 37.68,
                }
            ]
        )
        entries = parse_pg_stat_statements(raw)
        assert len(entries) == 1
        e = entries[0]
        assert e.query_text == "SELECT * FROM orders WHERE status = $1"
        assert e.calls == 120
        assert e.total_time_ms == 4521.33
        assert e.source == "pg_stat_statements"

    def test_json_array_with_pre_pg13_column_names(self):
        raw = json.dumps([{"query": "SELECT 1", "calls": 5, "total_time": 100.0, "mean_time": 20.0}])
        entries = parse_pg_stat_statements(raw)
        assert entries[0].total_time_ms == 100.0

    def test_derives_total_from_mean_and_calls_when_total_missing(self):
        raw = json.dumps([{"query": "SELECT 1", "calls": 10, "mean_exec_time": 5.0}])
        entries = parse_pg_stat_statements(raw)
        assert entries[0].total_time_ms == 50.0

    def test_psql_pipe_table_format(self):
        raw = (
            "                query                 | calls | total_time \n"
            "---------------------------------------+-------+------------\n"
            " SELECT * FROM orders WHERE id = $1     |   120 |    4521.33 \n"
        )
        entries = parse_pg_stat_statements(raw)
        assert len(entries) == 1
        assert entries[0].calls == 120
        assert entries[0].total_time_ms == 4521.33

    def test_csv_format(self):
        raw = "query,calls,total_time\nSELECT * FROM orders,50,1000.5\n"
        entries = parse_pg_stat_statements(raw)
        assert len(entries) == 1
        assert entries[0].query_text == "SELECT * FROM orders"
        assert entries[0].total_time_ms == 1000.5

    def test_rows_missing_query_text_are_skipped(self):
        raw = json.dumps([{"calls": 5, "total_time": 10.0}])
        assert parse_pg_stat_statements(raw) == []

    def test_empty_input(self):
        assert parse_pg_stat_statements("") == []
        assert parse_pg_stat_statements(None) == []


class TestPerformanceSchema:
    def test_json_array_picoseconds_converted_to_ms(self):
        raw = json.dumps(
            [
                {
                    "digest_text": "SELECT * FROM `orders` WHERE `status` = ?",
                    "count_star": 200,
                    "sum_timer_wait": 4_521_330_000_000,  # picoseconds
                }
            ]
        )
        entries = parse_performance_schema(raw)
        assert len(entries) == 1
        e = entries[0]
        assert e.calls == 200
        assert abs(e.total_time_ms - 4521.33) < 0.01
        assert e.source == "performance_schema"

    def test_derives_total_from_avg_timer_wait_and_count(self):
        raw = json.dumps(
            [{"digest_text": "SELECT 1", "count_star": 10, "avg_timer_wait": 1_000_000_000}]  # 1ms each
        )
        entries = parse_performance_schema(raw)
        assert abs(entries[0].total_time_ms - 10.0) < 0.001

    def test_mysql_pipe_table_format(self):
        raw = (
            "+----------------------------------+------------+-----------------+\n"
            "| digest_text                       | count_star | sum_timer_wait  |\n"
            "+----------------------------------+------------+-----------------+\n"
            "| SELECT * FROM orders WHERE id = ? | 50         | 1000000000000   |\n"
            "+----------------------------------+------------+-----------------+\n"
        )
        entries = parse_performance_schema(raw)
        assert len(entries) == 1
        assert entries[0].calls == 50
        assert abs(entries[0].total_time_ms - 1000.0) < 0.01


class TestQueryStore:
    def test_json_array_microseconds_converted_to_ms(self):
        raw = json.dumps(
            [{"query_sql_text": "SELECT * FROM orders WHERE id = @id", "count_executions": 30, "avg_duration": 5000}]
        )
        entries = parse_query_store(raw)
        assert len(entries) == 1
        e = entries[0]
        assert e.calls == 30
        # avg 5ms * 30 calls = 150ms total
        assert abs(e.total_time_ms - 150.0) < 0.01
        assert e.source == "query_store"

    def test_tsv_format_ssms_grid_copy(self):
        raw = "query_sql_text\tcount_executions\tavg_duration\nSELECT * FROM orders\t10\t2000\n"
        entries = parse_query_store(raw)
        assert len(entries) == 1
        assert entries[0].calls == 10
        assert abs(entries[0].total_time_ms - 20.0) < 0.01

    def test_total_duration_used_directly_when_present(self):
        raw = json.dumps([{"query_sql_text": "SELECT 1", "count_executions": 5, "total_duration": 25000}])
        entries = parse_query_store(raw)
        assert abs(entries[0].total_time_ms - 25.0) < 0.01


class TestRankTopN:
    def _entry(self, text, total_ms):
        return parse_pg_stat_statements(json.dumps([{"query": text, "calls": 1, "total_time": total_ms}]))[0]

    def test_sorts_by_total_time_descending(self):
        a = self._entry("A", 10)
        b = self._entry("B", 500)
        c = self._entry("C", 100)
        ranked = rank_top_n([a, b, c], n=3)
        assert [e.query_text for e in ranked] == ["B", "C", "A"]

    def test_caps_at_n(self):
        entries = [self._entry(str(i), i) for i in range(10)]
        ranked = rank_top_n(entries, n=3)
        assert len(ranked) == 3
        assert [e.query_text for e in ranked] == ["9", "8", "7"]

    def test_entries_with_no_time_signal_sort_last_not_dropped(self):
        raw = json.dumps([{"query": "no timing data"}])
        no_signal = parse_pg_stat_statements(raw)[0]
        assert no_signal.total_time_ms is None
        timed = self._entry("timed", 5.0)

        ranked = rank_top_n([no_signal, timed], n=2)
        assert [e.query_text for e in ranked] == ["timed", "no timing data"]


class TestNormalizedTextCaveat:
    """Design doc item 3: confirms the placeholder syntax these two
    normalized-text sources actually hand back doesn't silently break the
    existing heuristic engine's column/predicate extraction."""

    def test_postgres_dollar_placeholder_where_column_still_extracted(self):
        raw = json.dumps([{"query": "SELECT * FROM orders WHERE status = $1 AND customer_id = $2", "calls": 1}])
        entry = parse_pg_stat_statements(raw)[0]

        parser = QueryParser()
        parsed = parser.parse(entry.query_text)
        suggestions = IndexRecommender().recommend(query=entry.query_text, parsed=parsed, db_type="postgresql")

        columns_flagged = {c for s in suggestions if s.get("columns") for c in s["columns"]}
        assert "status" in columns_flagged
        assert "customer_id" in columns_flagged

    def test_mysql_question_mark_placeholder_where_column_still_extracted(self):
        raw = json.dumps([{"digest_text": "SELECT * FROM `orders` WHERE `status` = ?", "count_star": 1}])
        entry = parse_performance_schema(raw)[0]

        parser = QueryParser()
        parsed = parser.parse(entry.query_text)
        suggestions = IndexRecommender().recommend(query=entry.query_text, parsed=parsed, db_type="mysql")

        # Backtick-quoted identifiers from performance_schema's digest_text
        # — confirms these don't silently break column extraction either.
        columns_flagged = {c for s in suggestions if s.get("columns") for c in s["columns"]}
        assert "status" in columns_flagged
