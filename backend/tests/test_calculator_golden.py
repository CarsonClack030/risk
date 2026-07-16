from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from risk_backend.models.entities import (
    PollutantConcentration,
    SelectedPollutant,
    SiteSelection,
)
from risk_backend.repositories import database
from risk_backend.repositories.catalog import CatalogRepository
from risk_backend.repositories.parameters import ParameterRepository
from risk_backend.services.calculator import RiskCalculator

ALL_PATHWAYS = {
    "ois": True,
    "dcs": True,
    "pis": True,
    "dgw": True,
    "cgw": True,
    "iov3": True,
    "iiv2": True,
    "iov1": True,
    "iov2": True,
    "iiv1": True,
}
CONCENTRATIONS = {
    2: ("20", "3", "0.2", "0.8"),
    23: ("10", "5", "0.5", "1"),
}


class CalculatorGoldenTests(unittest.TestCase):
    def test_representative_results_match_released_formula_baseline(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "calculator_golden.json"
        expected = json.loads(fixture_path.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            runtime_database = Path(directory) / "risk.db"
            shutil.copy2(database.TEMPLATE_DB, runtime_database)
            with sqlite3.connect(runtime_database) as connection:
                connection.execute(
                    f"pragma user_version = {database.DATABASE_SCHEMA_VERSION}"
                )

            with patch.object(database, "RUNTIME_DB", runtime_database):
                selected = self._selected_pollutants()
                calculator = RiskCalculator(ParameterRepository())
                for standard, area_type in (
                    ("G", "I"),
                    ("G", "II"),
                    ("Z", "I"),
                    ("Z", "II"),
                ):
                    key = f"{standard}-{area_type}"
                    actual = calculator.calculate(
                        SiteSelection(standard, area_type),
                        selected,
                        ALL_PATHWAYS,
                    )
                    self._assert_snapshot(actual, expected[key])

    @staticmethod
    def _selected_pollutants() -> list[SelectedPollutant]:
        repository = CatalogRepository()
        selected: list[SelectedPollutant] = []
        for workspace_number, pollutant_id in enumerate(CONCENTRATIONS, start=1):
            pollutant = repository.get_pollutant(pollutant_id)
            if pollutant is None:
                raise AssertionError(f"测试污染物不存在：{pollutant_id}")
            concentration = PollutantConcentration(
                workspace_number=workspace_number,
                pollutant_id=pollutant.id,
                name=pollutant.name,
                english_name=pollutant.english_name,
                surface_concentration=Decimal(CONCENTRATIONS[pollutant_id][0]),
                lower_soil_concentration=Decimal(CONCENTRATIONS[pollutant_id][1]),
                groundwater_concentration=Decimal(CONCENTRATIONS[pollutant_id][2]),
                groundwater_protection_concentration=Decimal(
                    CONCENTRATIONS[pollutant_id][3]
                ),
            )
            selected.append(
                SelectedPollutant(workspace_number, pollutant, concentration)
            )
        return selected

    def _assert_snapshot(
        self,
        actual: dict[int, dict[str, dict[str, Decimal]]],
        expected: dict[str, dict[str, dict[str, str]]],
    ) -> None:
        for workspace_number, pollutant_id in enumerate(CONCENTRATIONS, start=1):
            for table, values in expected[str(pollutant_id)].items():
                for column, raw_expected in values.items():
                    with self.subTest(
                        pollutant_id=pollutant_id,
                        table=table,
                        column=column,
                    ):
                        expected_value = Decimal(raw_expected)
                        actual_value = actual[workspace_number][table][column]
                        tolerance = max(
                            Decimal("1e-24"),
                            abs(expected_value) * Decimal("1e-12"),
                        )
                        self.assertLessEqual(
                            abs(actual_value - expected_value), tolerance
                        )


if __name__ == "__main__":
    unittest.main()
