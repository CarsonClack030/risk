from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from risk_backend.application import RiskBackend
from risk_backend.models.entities import SiteSelection
from risk_backend.repositories.parameters import PARAMETER_NAMES
from risk_backend.services.calculator import RiskCalculator


class FakeParameterRepository:
    def __init__(self, values: dict[str, Decimal]):
        self.values = values

    def get_parameter_map(self, _selection: SiteSelection) -> dict[str, Decimal]:
        return dict(self.values)


def valid_parameter_values() -> dict[str, Decimal]:
    values = {name: Decimal("1") for name in PARAMETER_NAMES}
    values.update(
        {
            "Eit": Decimal("0.0005"),
            "Pws": Decimal("0.2"),
            "Rho_b": Decimal("1.5"),
            "Rho_s": Decimal("2.65"),
            "Theta_acap": Decimal("0.038"),
            "Theta_wcap": Decimal("0.342"),
            "Theta_acrack": Decimal("0.26"),
            "Theta_wcrack": Decimal("0.12"),
        }
    )
    return values


class ParameterValidationTests(unittest.TestCase):
    def validate(
        self, values: dict[str, Decimal], standard: str = "G", area_type: str = "I"
    ) -> None:
        calculator = RiskCalculator(FakeParameterRepository(values))
        calculator.validate_parameters(SiteSelection(standard, area_type), values)

    def test_valid_parameters_pass(self) -> None:
        self.validate(valid_parameter_values())

    def test_second_type_allows_zero_child_weight(self) -> None:
        values = valid_parameter_values()
        values["BWc"] = Decimal("0")
        self.validate(values, area_type="II")

    def test_non_finite_parameter_has_clear_error(self) -> None:
        values = valid_parameter_values()
        values["Pws"] = Decimal("NaN")
        with self.assertRaisesRegex(ValueError, "Pws=NaN 不是有限数字"):
            self.validate(values)

    def test_zero_denominator_parameter_has_clear_error(self) -> None:
        values = valid_parameter_values()
        values["BWa"] = Decimal("0")
        with self.assertRaisesRegex(ValueError, "成人平均体重.*必须大于 0"):
            self.validate(values)

    def test_negative_air_porosity_has_clear_error(self) -> None:
        values = valid_parameter_values()
        values["Pws"] = Decimal("0.5")
        with self.assertRaisesRegex(ValueError, "土壤空气孔隙率小于 0"):
            self.validate(values, standard="Z", area_type="II")

    def test_invalid_crack_porosity_sum_has_clear_error(self) -> None:
        values = valid_parameter_values()
        values["Theta_acrack"] = Decimal("0.8")
        values["Theta_wcrack"] = Decimal("0.4")
        with self.assertRaisesRegex(ValueError, "地基裂隙总孔隙体积比"):
            self.validate(values)

    def test_invalid_selection_is_rejected_before_parameter_lookup(self) -> None:
        calculator = RiskCalculator(FakeParameterRepository(valid_parameter_values()))
        with self.assertRaisesRegex(ValueError, "适用标准"):
            calculator.calculate(
                SiteSelection("DROP", "I"),
                [],
                {"ois": True},
            )

    def test_invalid_log_domain_has_clear_error(self) -> None:
        values = valid_parameter_values()
        values["Z_crack"] = Decimal("0.0001")
        with self.assertRaisesRegex(ValueError, "对数无效"):
            self.validate(values)

    def test_string_false_is_not_treated_as_selected_pathway(self) -> None:
        backend = RiskBackend.__new__(RiskBackend)
        backend.workspace_repository = MagicMock()
        backend.workspace_repository.list_selected_pollutants.return_value = [object()]
        backend.calculator = MagicMock()

        with self.assertRaisesRegex(ValueError, "至少选择一个暴露途径"):
            backend.calculate({"pathways": {"ois": "false"}})

        backend.calculator.calculate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
