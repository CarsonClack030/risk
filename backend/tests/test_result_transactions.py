from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from risk_backend.application import RiskBackend
from risk_backend.repositories.results import ResultRepository


class ResultTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "results.db"
        with sqlite3.connect(self.database_path) as connection:
            for table, columns in ResultRepository.RESET_SQL.items():
                column_sql = ", ".join(f"{column} real" for column in columns)
                connection.execute(
                    f"create table {table} (number integer primary key, {column_sql})"
                )
                connection.execute(f"insert into {table} (number) values (1)")
                connection.execute(
                    f"update {table} set {columns[0]} = 99 where number = 1"
                )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @contextmanager
    def connect_to_test_database(self):
        connection = sqlite3.connect(self.database_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def test_replace_results_updates_multiple_tables_in_one_transaction(self) -> None:
        results = {
            1: {
                "db_cr": {"CR_sn": Decimal("0.25")},
                "db_hq": {"HI_sn": Decimal("1.5")},
            }
        }
        with patch(
            "risk_backend.repositories.results.connect",
            self.connect_to_test_database,
        ):
            ResultRepository().replace_results(results)

        with sqlite3.connect(self.database_path) as connection:
            cr_value = connection.execute("select CR_sn from db_cr").fetchone()[0]
            hq_value = connection.execute("select HI_sn from db_hq").fetchone()[0]
        self.assertEqual(cr_value, 0.25)
        self.assertEqual(hq_value, 1.5)

    def test_database_error_rolls_back_reset_and_every_update(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                create trigger reject_hq_update before update on db_hq
                begin
                    select raise(abort, 'simulated write failure');
                end
                """
            )

        results = {
            1: {
                "db_cr": {"CR_ois": Decimal("0.25")},
                "db_hq": {"HQ_ois": Decimal("1.5")},
            }
        }
        with (
            patch(
                "risk_backend.repositories.results.connect",
                self.connect_to_test_database,
            ),
            self.assertRaisesRegex(sqlite3.IntegrityError, "simulated write failure"),
        ):
            ResultRepository().replace_results(results)

        with sqlite3.connect(self.database_path) as connection:
            cr_old_value = connection.execute("select CR_ois from db_cr").fetchone()[0]
            hq_old_value = connection.execute("select HQ_ois from db_hq").fetchone()[0]
        self.assertEqual(cr_old_value, 99)
        self.assertEqual(hq_old_value, 99)

    def test_invalid_result_column_is_rejected_before_opening_transaction(self) -> None:
        connect_mock = MagicMock()
        with (
            patch("risk_backend.repositories.results.connect", connect_mock),
            self.assertRaisesRegex(ValueError, "不支持的列"),
        ):
            ResultRepository().replace_results(
                {1: {"db_cr": {"unexpected_column": Decimal("1")}}}
            )
        connect_mock.assert_not_called()


class CalculationPersistenceOrderTests(unittest.TestCase):
    def test_calculation_failure_never_clears_previous_results(self) -> None:
        backend = RiskBackend.__new__(RiskBackend)
        backend.workspace_repository = MagicMock()
        backend.workspace_repository.list_selected_pollutants.return_value = [object()]
        backend.calculator = MagicMock()
        backend.calculator.calculate.side_effect = ValueError("formula failed")
        backend.result_repository = MagicMock()

        with self.assertRaisesRegex(ValueError, "formula failed"):
            backend.calculate(
                {
                    "standard": "G",
                    "area_type": "I",
                    "pathways": {"ois": True},
                }
            )

        backend.result_repository.replace_results.assert_not_called()
        backend.result_repository.reset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
