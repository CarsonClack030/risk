from __future__ import annotations

import sqlite3
import unittest
from decimal import Decimal

from risk_backend.api_server import serialize_parameter_group
from risk_backend.models.entities import ParameterRow
from risk_backend.repositories.database import TEMPLATE_DB
from risk_backend.repositories.parameters import PARAMETER_GROUPS, PARAMETER_NAMES, PARAMETER_UNITS


class ParameterUnitTests(unittest.TestCase):
    def test_every_calculation_parameter_has_a_unit(self) -> None:
        """新增计算参数时必须同步补充单位，避免界面出现空白单元格。"""
        self.assertEqual(set(PARAMETER_UNITS), set(PARAMETER_NAMES))
        self.assertTrue(all(PARAMETER_UNITS.values()))

        with sqlite3.connect(TEMPLATE_DB) as connection:
            database_names = {row[0] for row in connection.execute("select name from db_pol_area_par")}
        self.assertEqual(set(PARAMETER_UNITS), database_names)

    def test_representative_units_match_parameter_dimensions(self) -> None:
        self.assertEqual(PARAMETER_UNITS["A"], "cm²")
        self.assertEqual(PARAMETER_UNITS["Uair"], "cm·s⁻¹")
        self.assertEqual(PARAMETER_UNITS["BWa"], "kg")
        self.assertEqual(PARAMETER_UNITS["ACR"], "无量纲")
        self.assertEqual(PARAMETER_UNITS["tc"], "h")

    def test_parameter_api_serializes_unit_as_a_separate_field(self) -> None:
        row = ParameterRow(
            name="BWa",
            label="成人平均体重",
            unit="kg",
            data_gi=Decimal("61.8"),
            data_gii=Decimal("61.8"),
            data_zi=Decimal("52.6"),
            data_zii=Decimal("52.6"),
            group_id=4,
        )

        payload = serialize_parameter_group(4, [row])

        self.assertEqual(payload["title"], PARAMETER_GROUPS[4])
        self.assertEqual(payload["rows"][0]["unit"], "kg")
        self.assertEqual(payload["rows"][0]["data_gi"], 61.8)


if __name__ == "__main__":
    unittest.main()
