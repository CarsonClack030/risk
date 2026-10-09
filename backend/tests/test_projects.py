from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from risk_backend.application import RiskBackend
import risk_backend.repositories.database as database
from risk_backend.repositories.operation_logs import OperationLogRepository


class ProjectDatabaseTests(unittest.TestCase):
    def make_runtime_database(self, directory: str) -> Path:
        runtime_path = Path(directory) / "risk_app.db"
        shutil.copy2(database.TEMPLATE_DB, runtime_path)
        with sqlite3.connect(runtime_path) as connection:
            connection.execute("pragma user_version = 1")
        return runtime_path

    def test_new_project_restores_parameter_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_path = self.make_runtime_database(directory)
            with (
                patch.object(database, "RUNTIME_DB", runtime_path),
                patch.object(database, "APP_DIR", Path(directory)),
            ):
                backend = RiskBackend()
                backend.operation_log_repository.append(
                    level="info",
                    action="旧项目操作",
                    message="这条记录不应带入新项目",
                )
                with database.connect() as connection:
                    default_value = connection.execute(
                        "select data_GI from db_pol_area_par where name = 'A'"
                    ).fetchone()[0]
                    connection.execute(
                        "update db_pol_area_par_temp set data_GI = ? where name = 'A'",
                        (123.456,),
                    )

                backend.create_project(
                    {
                        "name": "新项目",
                        "standard": "G",
                        "area_type": "I",
                        "pathways": {},
                    }
                )

                with database.connect() as connection:
                    actual_value = connection.execute(
                        "select data_GI from db_pol_area_par_temp where name = 'A'"
                    ).fetchone()[0]
                self.assertEqual(actual_value, default_value)
                logs = backend.operation_log_repository.list_recent()
                self.assertFalse(
                    any(log["message"] == "这条记录不应带入新项目" for log in logs)
                )
                self.assertTrue(any(log["message"] == "新建了项目" for log in logs))

    def test_project_snapshot_can_replace_runtime_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_path = self.make_runtime_database(directory)
            project_path = Path(directory) / "project.riskproj"
            shutil.copy2(database.TEMPLATE_DB, project_path)
            with sqlite3.connect(project_path) as connection:
                connection.execute("pragma user_version = 1")
                connection.execute("delete from db_pol_temp")
                connection.commit()

            with (
                patch.object(database, "RUNTIME_DB", runtime_path),
                patch.object(database, "APP_DIR", Path(directory)),
                patch.object(database, "ensure_database", return_value=runtime_path),
            ):
                database.replace_runtime_database(project_path.read_bytes())

            with sqlite3.connect(runtime_path) as connection:
                self.assertEqual(
                    connection.execute("select count(*) from db_pol_temp").fetchone()[
                        0
                    ],
                    0,
                )
                self.assertIsNotNone(
                    connection.execute(
                        "select name from sqlite_master where name = ?",
                        (database.PROJECT_METADATA_TABLE,),
                    ).fetchone()
                )
                self.assertIsNotNone(
                    connection.execute(
                        "select name from sqlite_master where name = ?",
                        (database.OPERATION_LOG_TABLE,),
                    ).fetchone()
                )
            self.assertTrue(list(Path(directory).glob("risk_app.backup-*.db")))

    def test_operation_logs_are_exported_with_project_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_path = self.make_runtime_database(directory)
            database._migrate_database(runtime_path, existing_database=False)
            with (
                patch.object(database, "RUNTIME_DB", runtime_path),
                patch.object(database, "APP_DIR", Path(directory)),
                patch.object(database, "ensure_database", return_value=runtime_path),
            ):
                repository = OperationLogRepository()
                repository.append(
                    level="error",
                    action="风险计算",
                    message="风险计算失败",
                    details="参数不能为负数",
                    change_details="参数：PM10；原值：0.077；新值：0.119",
                )
                logs = repository.list_recent()
                csv_data = repository.export_csv()
                snapshot = database.export_project_database()

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["level"], "error")
            self.assertEqual(
                logs[0]["details"], "参数不能为负数；参数：PM10；原值：0.077；新值：0.119"
            )
            self.assertIn("风险计算失败", csv_data.decode("utf-8-sig"))
            self.assertIn("详细信息", csv_data.decode("utf-8-sig"))
            self.assertNotIn("修改详情", csv_data.decode("utf-8-sig"))
            snapshot_path = Path(directory) / "snapshot.riskproj"
            snapshot_path.write_bytes(snapshot)
            with sqlite3.connect(snapshot_path) as connection:
                self.assertEqual(
                    connection.execute(
                        f"select count(*) from {database.OPERATION_LOG_TABLE}"
                    ).fetchone()[0],
                    1,
                )

    def test_project_metadata_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_path = self.make_runtime_database(directory)
            database._migrate_database(runtime_path, existing_database=False)
            with (
                patch.object(database, "RUNTIME_DB", runtime_path),
                patch.object(database, "APP_DIR", Path(directory)),
                patch.object(database, "ensure_database", return_value=runtime_path),
            ):
                saved = database.write_project_metadata(
                    name="某地块评估",
                    standard="Z",
                    area_type="II",
                    pathways={"dgw": True, "ois": False},
                )
                loaded = database.read_project_metadata()

            self.assertEqual(loaded, saved)
            self.assertEqual(loaded["name"], "某地块评估")
            self.assertEqual(loaded["standard"], "Z")
            self.assertEqual(loaded["area_type"], "II")
            self.assertTrue(loaded["pathways"]["dgw"])
            self.assertFalse(loaded["pathways"]["ois"])

    def test_invalid_project_does_not_replace_runtime_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_path = self.make_runtime_database(directory)
            original = runtime_path.read_bytes()

            with (
                patch.object(database, "RUNTIME_DB", runtime_path),
                patch.object(database, "APP_DIR", Path(directory)),
                patch.object(database, "ensure_database", return_value=runtime_path),
                self.assertRaisesRegex(ValueError, "项目文件数据库校验失败"),
            ):
                database.replace_runtime_database(b"not-a-sqlite-project")

            self.assertEqual(runtime_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
