"""Convert domain objects and result tables into API-friendly values."""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from risk_backend.models.entities import ParameterRow, Pollutant, SelectedPollutant
from risk_backend.repositories.parameters import PARAMETER_GROUPS
from risk_backend.repositories.results import ResultRepository


class ResultConfig(TypedDict):
    """Describe the database and display columns for one result table."""

    table: str
    title: str
    columns: tuple[str, ...]
    headers: tuple[str, ...]
    display_columns: tuple[str, ...]


RESULT_CONFIGS: tuple[ResultConfig, ...] = (
    {
        "table": "db_exposure_ca",
        "title": "暴露量-致癌",
        "columns": (
            "ID",
            "p_name",
            "OISER_ca",
            "DCSER_ca",
            "PISER_ca",
            "IOVER_ca1",
            "IOVER_ca2",
            "IIVER_ca1",
            "IOVER_ca3",
            "IIVER_ca2",
            "DGWER_ca",
            "CGWER_ca",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "口摄入土壤颗粒物",
            "皮肤接触土壤颗粒物",
            "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物",
            "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物",
            "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物",
            "皮肤接触地下水",
            "饮用地下水",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "OISER_ca",
            "DCSER_ca",
            "PISER_ca",
            "IOVER_ca1",
            "IOVER_ca2",
            "IIVER_ca1",
            "IOVER_ca3",
            "IIVER_ca2",
            "DGWER_ca",
            "CGWER_ca",
        ),
    },
    {
        "table": "db_exposure_nc",
        "title": "暴露量-非致癌",
        "columns": (
            "ID",
            "p_name",
            "OISER_nc",
            "DCSER_nc",
            "PISER_nc",
            "IOVER_nc1",
            "IOVER_nc2",
            "IIVER_nc1",
            "IOVER_nc3",
            "IIVER_nc2",
            "DGWER_nc",
            "CGWER_nc",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "口摄入土壤颗粒物",
            "皮肤接触土壤颗粒物",
            "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物",
            "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物",
            "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物",
            "皮肤接触地下水",
            "饮用地下水",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "OISER_nc",
            "DCSER_nc",
            "PISER_nc",
            "IOVER_nc1",
            "IOVER_nc2",
            "IIVER_nc1",
            "IOVER_nc3",
            "IIVER_nc2",
            "DGWER_nc",
            "CGWER_nc",
        ),
    },
    {
        "table": "db_cr",
        "title": "风险-致癌",
        "columns": (
            "ID",
            "p_name",
            "CR_ois",
            "CR_dcs",
            "CR_pis",
            "CR_iov1",
            "CR_iov2",
            "CR_iiv1",
            "CR_sn",
            "CR_iov3",
            "CR_iiv2",
            "CR_dgw",
            "CR_cgw",
            "CR_wn",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "口摄入土壤颗粒物",
            "皮肤接触土壤颗粒物",
            "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物",
            "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物",
            "合计",
            "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物",
            "皮肤接触地下水",
            "饮用地下水",
            "合计",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "CR_ois",
            "CR_dcs",
            "CR_pis",
            "CR_iov1",
            "CR_iov2",
            "CR_iiv1",
            "CR_sn",
            "CR_iov3",
            "CR_iiv2",
            "CR_dgw",
            "CR_cgw",
            "CR_wn",
        ),
    },
    {
        "table": "db_hq",
        "title": "风险-危害商",
        "columns": (
            "ID",
            "p_name",
            "HQ_ois",
            "HQ_dcs",
            "HQ_pis",
            "HQ_iov1",
            "HQ_iov2",
            "HQ_iiv1",
            "HI_sn",
            "HQ_iov3",
            "HQ_iiv2",
            "HQ_dgw",
            "HQ_cgw",
            "HI_wn",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "口摄入土壤颗粒物",
            "皮肤接触土壤颗粒物",
            "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物",
            "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物",
            "合计",
            "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物",
            "皮肤接触地下水",
            "饮用地下水",
            "合计",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "HQ_ois",
            "HQ_dcs",
            "HQ_pis",
            "HQ_iov1",
            "HQ_iov2",
            "HQ_iiv1",
            "HI_sn",
            "HQ_iov3",
            "HQ_iiv2",
            "HQ_dgw",
            "HQ_cgw",
            "HI_wn",
        ),
    },
    {
        "table": "db_pcr",
        "title": "贡献率-致癌",
        "columns": (
            "ID",
            "p_name",
            "PCR_ois",
            "PCR_dcs",
            "PCR_pis",
            "PCR_iov1",
            "PCR_iov2",
            "PCR_iiv1",
            "PCR_sn",
            "PCR_iov3",
            "PCR_iiv2",
            "PCR_dgw",
            "PCR_cgw",
            "PCR_wn",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "口摄入土壤颗粒物",
            "皮肤接触土壤颗粒物",
            "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物",
            "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物",
            "合计",
            "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物",
            "皮肤接触地下水",
            "饮用地下水",
            "合计",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "PCR_ois",
            "PCR_dcs",
            "PCR_pis",
            "PCR_iov1",
            "PCR_iov2",
            "PCR_iiv1",
            "PCR_sn",
            "PCR_iov3",
            "PCR_iiv2",
            "PCR_dgw",
            "PCR_cgw",
            "PCR_wn",
        ),
    },
    {
        "table": "db_phq",
        "title": "贡献率-非致癌",
        "columns": (
            "ID",
            "p_name",
            "PHQ_ois",
            "PHQ_dcs",
            "PHQ_pis",
            "PHQ_iov1",
            "PHQ_iov2",
            "PHQ_iiv1",
            "PHI_sn",
            "PHQ_iov3",
            "PHQ_iiv2",
            "PHQ_dgw",
            "PHQ_cgw",
            "PHI_wn",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "口摄入土壤颗粒物",
            "皮肤接触土壤颗粒物",
            "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物",
            "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物",
            "合计",
            "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物",
            "皮肤接触地下水",
            "饮用地下水",
            "合计",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "PHQ_ois",
            "PHQ_dcs",
            "PHQ_pis",
            "PHQ_iov1",
            "PHQ_iov2",
            "PHQ_iiv1",
            "PHI_sn",
            "PHQ_iov3",
            "PHQ_iiv2",
            "PHQ_dgw",
            "PHQ_cgw",
            "PHI_wn",
        ),
    },
    {
        "table": "db_cv",
        "title": "风险控制值",
        "columns": (
            "ID",
            "p_name",
            "RCVS_n",
            "HCVS_n",
            "RCVG_n",
            "HCVG_n",
            "CVS_pgw",
            "e_name",
            "number",
        ),
        "headers": (
            "序号",
            "污染物编号",
            "污染物名称",
            "土壤致癌风险控制值",
            "土壤非致癌风险控制值",
            "地下水致癌风险控制值",
            "地下水非致癌风险控制值",
            "保护地下水的土壤风险控制值",
        ),
        "display_columns": (
            "number",
            "ID",
            "p_name",
            "RCVS_n",
            "HCVS_n",
            "RCVG_n",
            "HCVG_n",
            "CVS_pgw",
        ),
    },
)

POLLUTANT_FIELDS = (
    "id",
    "name",
    "english_name",
    "henry",
    "da",
    "dw",
    "koc",
    "solubility",
    "sfo",
    "iur",
    "rfdo",
    "rfc",
    "absgi",
    "absd",
    "saf",
    "kp",
)


def json_value(value: object) -> object:
    """Convert Decimal values while leaving JSON-native values unchanged."""
    return float(value) if isinstance(value, Decimal) else value


def serialize_pollutant(pollutant: Pollutant) -> dict[str, object]:
    return {field: json_value(getattr(pollutant, field)) for field in POLLUTANT_FIELDS}


def serialize_selected(item: SelectedPollutant) -> dict[str, object]:
    concentration = item.concentration
    return {
        "workspace_number": item.workspace_number,
        "pollutant": serialize_pollutant(item.pollutant),
        "concentration": {
            "workspace_number": concentration.workspace_number,
            "pollutant_id": concentration.pollutant_id,
            "name": concentration.name,
            "english_name": concentration.english_name,
            "surface_concentration": json_value(concentration.surface_concentration),
            "lower_soil_concentration": json_value(
                concentration.lower_soil_concentration
            ),
            "groundwater_concentration": json_value(
                concentration.groundwater_concentration
            ),
            "groundwater_protection_concentration": json_value(
                concentration.groundwater_protection_concentration
            ),
        },
    }


def serialize_parameter_group(
    group_id: int, rows: list[ParameterRow]
) -> dict[str, object]:
    return {
        "id": group_id,
        "title": PARAMETER_GROUPS[group_id],
        "rows": [
            {
                "name": row.name,
                "label": row.label,
                "unit": row.unit,
                "data_gi": json_value(row.data_gi),
                "data_gii": json_value(row.data_gii),
                "data_zi": json_value(row.data_zi),
                "data_zii": json_value(row.data_zii),
                "group_id": row.group_id,
            }
            for row in rows
        ],
    }


def format_result_value(value: object) -> object:
    """Use scientific notation for calculated floats shown in result tables."""
    if value in (None, ""):
        return ""
    return f"{value:.2e}" if isinstance(value, float) else value


def serialize_results(result_repository: ResultRepository) -> list[dict[str, object]]:
    tables: list[dict[str, object]] = []
    for config in RESULT_CONFIGS:
        records = [
            dict(zip(config["columns"], row))
            for row in result_repository.fetch_table(config["table"])
        ]
        tables.append(
            {
                "key": config["table"],
                "title": config["title"],
                "headers": list(config["headers"]),
                "rows": [
                    [
                        format_result_value(record[column])
                        for column in config["display_columns"]
                    ]
                    for record in records
                ],
            }
        )
    return tables


def build_export_rows(result_repository: ResultRepository) -> list[list[str]]:
    rows: list[list[str]] = []
    for table in serialize_results(result_repository):
        rows.append([str(table["title"])])
        rows.append([str(header) for header in table["headers"]])
        rows.extend([[str(cell) for cell in row] for row in table["rows"]])
        rows.append([])
    return rows
