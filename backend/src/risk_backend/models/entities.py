from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


ZERO = Decimal("0")


def to_decimal(value: Any, default: Decimal = ZERO) -> Decimal:
    if value in (None, "", "None"):
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


@dataclass
class Pollutant:
    id: int
    name: str
    english_name: str
    henry: Decimal
    da: Decimal
    dw: Decimal
    koc: Decimal
    solubility: Decimal
    sfo: Decimal
    iur: Decimal
    rfdo: Decimal
    rfc: Decimal
    absgi: Decimal
    absd: Decimal
    saf: Decimal
    kp: Decimal


@dataclass
class PollutantConcentration:
    workspace_number: int
    pollutant_id: int
    name: str
    english_name: str
    surface_concentration: Decimal
    lower_soil_concentration: Decimal
    groundwater_concentration: Decimal
    groundwater_protection_concentration: Decimal


@dataclass
class SelectedPollutant:
    workspace_number: int
    pollutant: Pollutant
    concentration: PollutantConcentration


@dataclass
class ParameterRow:
    name: str
    label: str
    data_gi: Decimal
    data_gii: Decimal
    data_zi: Decimal
    data_zii: Decimal
    group_id: int


@dataclass
class SiteSelection:
    standard: str
    area_type: str

    @property
    def db_column(self) -> str:
        return f"data_{self.standard}{self.area_type}"


@dataclass
class User:
    username: str
    password: str


class AttributeMap:
    def __init__(self, values: dict[str, Any]):
        self._values = values

    def __getattr__(self, item: str) -> Any:
        try:
            return self._values[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)
