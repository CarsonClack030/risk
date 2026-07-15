from __future__ import annotations

import unittest

from risk_backend.application import RiskBackend
from risk_backend.workspace_import import WorkspaceImporter


class ApplicationNumberValidationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
