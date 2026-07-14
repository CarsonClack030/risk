from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from risk_backend.api_server import RESULT_CONFIGS, serialize_results
from risk_backend.repositories.results import ResultRepository


class FakeResultRepository:
    """为序列化测试生成结构完整、内容最小的结果行。"""

    def fetch_table(self, table: str) -> list[list[object]]:
        config = next(item for item in RESULT_CONFIGS if item["table"] == table)
        values = {column: None for column in config["columns"]}
        values.update({"number": 7, "ID": 42, "p_name": "测试污染物"})
        return [[values[column] for column in config["columns"]]]


class ResultOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "results.db"
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                create table db_cv (
                    ID integer,
                    p_name text,
                    RCVS_n real,
                    HCVS_n real,
                    RCVG_n real,
                    HCVG_n real,
                    CVS_pgw real,
                    e_name text,
                    number integer
                )
                """
            )
            # 编号 17 重复出现，并故意让污染物编号顺序和工作区序号顺序不同。
            connection.executemany(
                "insert into db_cv values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (17, "苯", 30, None, None, None, None, "Benzene", 3),
                    (42, "砷（无机）", 10, None, None, None, None, "Arsenic", 1),
                    (17, "苯", 20, None, None, None, None, "Benzene", 2),
                ],
            )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @contextmanager
    def connect_to_test_database(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def test_fetch_table_orders_by_workspace_number(self) -> None:
        repository = ResultRepository()
        with patch("risk_backend.repositories.results.connect", self.connect_to_test_database):
            rows = repository.fetch_table("db_cv")

        self.assertEqual([row[-1] for row in rows], [1, 2, 3])
        self.assertEqual([row[0] for row in rows], [42, 17, 17])
        self.assertEqual([row[2] for row in rows], [10, 20, 30])

    def test_fetch_table_rejects_unknown_table(self) -> None:
        with self.assertRaisesRegex(ValueError, "不支持的结果表"):
            ResultRepository().fetch_table("db_not_a_result")

    def test_serialized_results_expose_workspace_number_first(self) -> None:
        tables = serialize_results(FakeResultRepository())

        self.assertEqual(len(tables), len(RESULT_CONFIGS))
        for table in tables:
            self.assertEqual(table["headers"][:3], ["序号", "污染物编号", "污染物名称"])
            self.assertEqual(table["rows"][0][:3], [7, 42, "测试污染物"])
            self.assertEqual(len(table["headers"]), len(table["rows"][0]))


if __name__ == "__main__":
    unittest.main()
