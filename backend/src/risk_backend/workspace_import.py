"""Parse tabular pollutant files and import them into the workspace."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from risk_backend.exporters import build_xlsx
from risk_backend.models.entities import Pollutant
from risk_backend.repositories.catalog import CatalogRepository
from risk_backend.repositories.workspace import WorkspaceRepository
from risk_backend.serialization import serialize_selected
from risk_backend.tabular_import import load_tabular_rows

EXCEL_COLUMN_ALIASES = {
    "pollutant_id": ("编号", "污染物编号", "污染物id", "id", "number", "pollutant_id"),
    "name": ("污染物名称", "名称", "name", "p_name"),
    "english_name": ("英文名", "英文名称", "english_name", "e_name"),
    "surface_concentration": (
        "地表浓度",
        "地表浓度（mg/kg）",
        "表层土壤浓度",
        "表层土壤浓度（mg/kg）",
        "surface_concentration",
    ),
    "lower_soil_concentration": (
        "下层土壤浓度",
        "下层土壤浓度（mg/kg）",
        "lower_soil_concentration",
    ),
    "groundwater_concentration": (
        "地下水浓度",
        "地下水浓度（mg/L）",
        "groundwater_concentration",
    ),
    "groundwater_protection_concentration": (
        "地下水保护浓度",
        "地下水保护浓度（mg/L）",
        "保护地下水浓度",
        "保护地下水浓度（mg/L）",
        "groundwater_protection_concentration",
    ),
}
EXCEL_IDENTIFIER_FIELDS = ("pollutant_id", "name", "english_name")
EXCEL_CONCENTRATION_FIELDS = (
    "surface_concentration",
    "lower_soil_concentration",
    "groundwater_concentration",
    "groundwater_protection_concentration",
)
EXCEL_REQUIRED_IDENTIFIER_TEXT = "污染物编号、污染物名称、英文名"
WORKSPACE_IMPORT_TEMPLATE_HEADERS = (
    "污染物编号",
    "污染物名称",
    "英文名",
    "地表浓度（mg/kg）",
    "下层土壤浓度（mg/kg）",
    "地下水浓度（mg/L）",
    "地下水保护浓度（mg/L）",
)
WORKSPACE_IMPORT_TEMPLATE_NOTICE = (
    "使用说明：支持上传 .xlsx / .xls / .csv / .txt；至少填写“污染物编号 / 污染物名称 / 英文名”其中之一；"
    "土壤浓度单位为 mg/kg，地下水浓度单位为 mg/L；四类浓度留空按 0 处理；"
    "模板示例行可保留，导入时会自动忽略。"
)
WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_MARKER = "模板示例（保留也会自动忽略）"
WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_ROW = (
    WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_MARKER,
    "苯",
    "Benzene",
    "1.25",
    "2.50",
    "0",
    "4.75",
)


def normalize_header(text: object) -> str:
    """Normalize common punctuation differences in imported column names."""
    raw = str(text or "").strip().lower()
    return "".join(char for char in raw if char not in " \t\r\n_-()[]{}（）【】")


NORMALIZED_EXCEL_ALIAS_MAP = {
    normalize_header(alias): field
    for field, aliases in EXCEL_COLUMN_ALIASES.items()
    for alias in aliases
}


class WorkspaceImporter:
    """Coordinate file parsing, catalog matching and workspace insertion."""

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.workspace_repository = workspace_repository

    def import_file(
        self,
        content: bytes,
        *,
        filename: str = "",
        content_type: str = "",
    ) -> dict[str, object]:
        if not content:
            raise ValueError("上传的文件为空")

        rows = load_tabular_rows(content, filename=filename, content_type=content_type)
        header_row_index, column_map = self.parse_columns(rows)
        imported_entries: list[dict[str, object]] = []
        errors: list[str] = []

        data_rows = rows[header_row_index + 1 :]
        for row_number, row in enumerate(data_rows, start=header_row_index + 2):
            if self._is_example_row(row) or not any(str(cell).strip() for cell in row):
                continue
            try:
                imported_entries.append(self._parse_row(column_map, row))
            except ValueError as exc:
                errors.append(f"第 {row_number} 行：{exc}")

        if errors:
            suffix = "；其余错误请修正后重试" if len(errors) > 5 else ""
            raise ValueError("文件导入失败：" + "；".join(errors[:5]) + suffix)
        if not imported_entries:
            raise ValueError("文件中没有可导入的数据行")

        imported_items = self.workspace_repository.import_pollutants(imported_entries)
        return {
            "items": [serialize_selected(item) for item in imported_items],
            "imported": len(imported_items),
            "total": self.workspace_repository.count_selected_pollutants(),
        }

    @staticmethod
    def build_template() -> bytes:
        return build_xlsx(
            [
                [WORKSPACE_IMPORT_TEMPLATE_NOTICE],
                list(WORKSPACE_IMPORT_TEMPLATE_HEADERS),
                list(WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_ROW),
                [],
            ]
        )

    @staticmethod
    def parse_columns(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
        """Return the header row index and canonical field-to-column mapping."""
        for row_index, row in enumerate(rows):
            column_map: dict[str, int] = {}
            for column_index, cell in enumerate(row):
                field = NORMALIZED_EXCEL_ALIAS_MAP.get(normalize_header(cell))
                if field:
                    column_map[field] = column_index

            if not column_map:
                continue
            if not any(field in column_map for field in EXCEL_IDENTIFIER_FIELDS):
                raise ValueError(
                    f"第 {row_index + 1} 行缺少标识列，至少需要 {EXCEL_REQUIRED_IDENTIFIER_TEXT} 之一"
                )
            return row_index, column_map
        raise ValueError(
            f"未识别到可用表头，至少需要 {EXCEL_REQUIRED_IDENTIFIER_TEXT} 之一"
        )

    def _parse_row(
        self,
        column_map: dict[str, int],
        row: list[str],
    ) -> dict[str, object]:
        return {
            "pollutant": self._resolve_pollutant(column_map, row),
            "surface_concentration": self._parse_decimal(
                self._cell(row, column_map, "surface_concentration"), "地表浓度"
            ),
            "lower_soil_concentration": self._parse_decimal(
                self._cell(row, column_map, "lower_soil_concentration"), "下层土壤浓度"
            ),
            "groundwater_concentration": self._parse_decimal(
                self._cell(row, column_map, "groundwater_concentration"), "地下水浓度"
            ),
            "groundwater_protection_concentration": self._parse_decimal(
                self._cell(row, column_map, "groundwater_protection_concentration"),
                "地下水保护浓度",
            ),
        }

    @staticmethod
    def _cell(row: list[str], column_map: dict[str, int], field: str) -> str:
        column_index = column_map.get(field)
        if column_index is None or column_index >= len(row):
            return ""
        return str(row[column_index]).strip()

    @staticmethod
    def _is_example_row(row: list[str]) -> bool:
        return any(
            str(cell).strip() == WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_MARKER
            for cell in row
        )

    @staticmethod
    def _parse_decimal(value: str, label: str) -> Decimal:
        if not value:
            return Decimal("0")
        try:
            parsed = Decimal(value.replace(",", ""))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{label}不是合法数字（当前值：{value}）") from None
        if not parsed.is_finite():
            raise ValueError(f"{label}必须是有限数字（当前值：{value}）")
        if parsed < 0:
            raise ValueError(f"{label}不能小于 0（当前值：{value}）")
        return parsed

    @staticmethod
    def _parse_pollutant_id(value: str) -> int | None:
        if not value:
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError(f"污染物编号不是合法数字（当前值：{value}）") from None
        if not parsed.is_finite() or parsed != parsed.to_integral_value():
            raise ValueError(f"污染物编号必须是整数（当前值：{value}）")
        return int(parsed)

    def _resolve_pollutant(
        self,
        column_map: dict[str, int],
        row: list[str],
    ) -> Pollutant:
        raw_id = self._cell(row, column_map, "pollutant_id")
        raw_name = self._cell(row, column_map, "name")
        raw_english_name = self._cell(row, column_map, "english_name")

        pollutant: Pollutant | None = None
        pollutant_id = self._parse_pollutant_id(raw_id)
        if pollutant_id is not None:
            pollutant = self.catalog_repository.get_pollutant(pollutant_id)
            if pollutant is None:
                raise ValueError(f"未找到编号为 {pollutant_id} 的污染物")

        if raw_name:
            by_name = self.catalog_repository.find_by_name(raw_name)
            if by_name is None:
                raise ValueError(f"未找到名称为“{raw_name}”的污染物")
            if pollutant and pollutant.id != by_name.id:
                raise ValueError("污染物编号和名称对应的不是同一条目录记录")
            pollutant = by_name

        if raw_english_name:
            by_english_name = self.catalog_repository.find_by_english_name(
                raw_english_name
            )
            if by_english_name is None:
                raise ValueError(f"未找到英文名为“{raw_english_name}”的污染物")
            if pollutant and pollutant.id != by_english_name.id:
                raise ValueError("污染物编号/名称和英文名对应的不是同一条目录记录")
            pollutant = by_english_name

        if pollutant is None:
            raise ValueError(f"至少需要填写 {EXCEL_REQUIRED_IDENTIFIER_TEXT} 之一")
        return pollutant
