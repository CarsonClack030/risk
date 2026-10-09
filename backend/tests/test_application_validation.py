from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import Mock

from risk_backend.application import RiskBackend
from risk_backend.models.entities import ParameterRow
from risk_backend.workspace_import import WorkspaceImporter


class ApplicationNumberValidationTests(unittest.TestCase):
    def test_new_project_clears_workspace_and_restores_default_parameters(self) -> None:
        backend = RiskBackend.__new__(RiskBackend)
        backend.workspace_repository = Mock()
        backend.parameter_repository = Mock()
        backend.operation_log_repository = Mock()
        backend.update_project_metadata = Mock()
        backend.record_operation = Mock()
        backend.health = Mock(return_value={"status": "ok"})
        payload = {
            "name": "测试项目",
            "standard": "G",
            "area_type": "I",
            "pathways": {},
        }

        result = backend.create_project(payload)

        backend.workspace_repository.clear_workspace.assert_called_once_with()
        backend.parameter_repository.reset_defaults.assert_called_once_with()
        backend.update_project_metadata.assert_called_once_with(payload)
        self.assertEqual(result, {"status": "ok"})

    def test_finite_decimal_accepts_regular_values(self) -> None:
        self.assertEqual(str(RiskBackend._parse_finite_decimal("1.25", "浓度")), "1.25")

    def test_finite_decimal_rejects_nan_and_infinity(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "有限数字"),
            ):
                RiskBackend._parse_finite_decimal(value, "浓度")

    def test_import_decimal_rejects_non_finite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "有限数字"):
            WorkspaceImporter._parse_decimal("NaN", "地表浓度")

    def test_concentration_rejects_negative_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能小于 0"):
            WorkspaceImporter._parse_decimal("-1", "地表浓度")

    def test_positive_integer_rejects_fraction_and_boolean(self) -> None:
        for value in ("1.5", True, 0):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "正整数"),
            ):
                RiskBackend._parse_positive_integer(value, "工作区序号")

    def test_parameter_change_log_contains_before_after_value_and_unit(self) -> None:
        recorded: list[dict[str, str]] = []

        class Recorder:
            def append(self, **payload: str) -> None:
                recorded.append(payload)

        backend = RiskBackend.__new__(RiskBackend)
        backend.operation_log_repository = Recorder()
        before = {
            (2, "PM10"): ParameterRow(
                name="PM10",
                label="空气中可吸入颗粒物",
                unit="mg·m⁻³",
                data_gi=Decimal("0.119"),
                data_gii=Decimal("0.119"),
                data_zi=Decimal("0.077"),
                data_zii=Decimal("0.077"),
                group_id=2,
            )
        }
        after = {
            (2, "PM10"): ParameterRow(
                name="PM10",
                label="空气中可吸入颗粒物",
                unit="mg·m⁻³",
                data_gi=Decimal("0.119"),
                data_gii=Decimal("0.119"),
                data_zi=Decimal("0.119"),
                data_zii=Decimal("0.077"),
                group_id=2,
            )
        }

        changed = backend._record_parameter_changes(before, after, "保存参数")

        self.assertEqual(changed, 1)
        self.assertIn("原值：0.077；新值：0.119", recorded[0]["details"])
        self.assertIn("单位：mg·m⁻³", recorded[0]["details"])
        self.assertIn("浙江标准·第一类用地", recorded[0]["details"])


if __name__ == "__main__":
    unittest.main()
