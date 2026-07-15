from __future__ import annotations

import unittest

from risk_backend.api_server import (
    EXCEL_CONCENTRATION_FIELDS,
    WORKSPACE_IMPORT_TEMPLATE_HEADERS,
    RiskBackend,
)


class ConcentrationUnitTests(unittest.TestCase):
    def test_download_template_includes_concentration_units(self) -> None:
        self.assertEqual(
            WORKSPACE_IMPORT_TEMPLATE_HEADERS[-4:],
            (
                "地表浓度（mg/kg）",
                "下层土壤浓度（mg/kg）",
                "地下水浓度（mg/L）",
                "地下水保护浓度（mg/L）",
            ),
        )

    def test_import_recognizes_headers_with_units(self) -> None:
        rows = [["污染物名称", *WORKSPACE_IMPORT_TEMPLATE_HEADERS[-4:]]]

        _, column_map = RiskBackend()._parse_excel_columns(rows)

        self.assertTrue(all(field in column_map for field in EXCEL_CONCENTRATION_FIELDS))

    def test_import_keeps_support_for_legacy_headers(self) -> None:
        rows = [["污染物名称", "地表浓度", "下层土壤浓度", "地下水浓度", "地下水保护浓度"]]

        _, column_map = RiskBackend()._parse_excel_columns(rows)

        self.assertTrue(all(field in column_map for field in EXCEL_CONCENTRATION_FIELDS))


if __name__ == "__main__":
    unittest.main()
