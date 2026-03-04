"""Tests for io/csv_utils.py."""

from evidence_collector.io.csv_utils import (
    append_result_row,
    init_results_csv,
    write_results_csv,
)


class TestInitResultsCsv:
    def test_writes_header(self, tmp_path):
        path = tmp_path / "results.csv"
        init_results_csv(path, ["id", "status", "url"])
        assert path.read_text().strip() == "id,status,url"


class TestAppendResultRow:
    def test_appends_correctly(self, tmp_path):
        path = tmp_path / "results.csv"
        init_results_csv(path, ["id", "status"])
        append_result_row(path, {"id": "s1", "status": "success"})
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert lines[1] == "s1,success"

    def test_missing_keys_produce_empty(self, tmp_path):
        path = tmp_path / "results.csv"
        init_results_csv(path, ["id", "status", "extra"])
        append_result_row(path, {"id": "s1"})
        lines = path.read_text().strip().split("\n")
        assert lines[1] == "s1,,"


class TestWriteResultsCsv:
    def test_derives_columns_and_writes(self, tmp_path):
        path = tmp_path / "results.csv"
        rows = [
            {"id": "1", "name": "alice"},
            {"id": "2", "name": "bob", "extra": "val"},
        ]
        write_results_csv(path, rows)
        lines = path.read_text().strip().split("\n")
        assert lines[0] == "id,name,extra"
        assert len(lines) == 3

    def test_empty_rows(self, tmp_path):
        path = tmp_path / "results.csv"
        write_results_csv(path, [])
        assert path.read_text() == ""
