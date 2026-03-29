from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from risk_backend.exporters import build_xlsx
from risk_backend.models.entities import (
    ParameterRow,
    Pollutant,
    PollutantConcentration,
    SelectedPollutant,
    SiteSelection,
)
from risk_backend.repositories.auth import AuthRepository
from risk_backend.repositories.catalog import CatalogRepository
from risk_backend.repositories.database import RUNTIME_DB, ensure_database
from risk_backend.repositories.parameters import PARAMETER_GROUPS, ParameterRepository
from risk_backend.repositories.results import ResultRepository
from risk_backend.repositories.workspace import WorkspaceRepository
from risk_backend.services.calculator import RiskCalculator
from risk_backend.xlsx import load_xlsx_rows


# 这里是 Python 后端的“HTTP 门面层”。
# 它的职责不是做公式本身，而是负责：
# 1. 把前端传来的 JSON 转成 Python 对象。
# 2. 调用仓储层 / 服务层执行业务动作。
# 3. 再把 Python 对象序列化成前端能直接消费的 JSON。
#
# 你可以把它理解成：
# 前端说“我要查目录”“我要开始计算”，
# api_server.py 负责把这些口语化请求翻译成后端内部动作。

# 前端勾选的路径 key 和原业务中文说明的对应表。
# 这份映射会被计算接口用于：
# - 校验所有路径字段是否齐全
# - 统一管理各条路径的语义名称
PATHWAY_LABELS = {
    "ois": "口摄入土壤颗粒物",
    "dcs": "皮肤接触土壤颗粒物",
    "pis": "吸入土壤颗粒物",
    "dgw": "皮肤接触地下水",
    "cgw": "饮用地下水",
    "iov3": "吸入室外空气中来自地下水的气态污染物",
    "iiv2": "吸入室内空气中来自地下水的气态污染物",
    "iov1": "吸入室外空气中来自表层土壤的气态污染物",
    "iov2": "吸入室外空气中来自下层土壤的气态污染物",
    "iiv1": "吸入室内空气中来自下层土壤的气态污染物",
}

# 结果表配置：
# 项目里最终要展示 7 张结果表，每一张表都包含：
# - table:          对应数据库表名
# - title:          前端标签页标题
# - columns:        数据库实际列顺序
# - headers:        前端展示表头
# - displayColumns: 真正需要给用户看的列
#
# 之所以集中在这里，而不是散落到多个函数中，
# 是因为“数据库列结构”和“前端展示结构”天然是一对多关系，
# 配置化以后，序列化和导出都能直接复用这份定义。
RESULT_CONFIGS = [
    {
        "table": "db_exposure_ca",
        "title": "暴露量-致癌",
        "columns": [
            "ID", "p_name", "OISER_ca", "DCSER_ca", "PISER_ca", "IOVER_ca1", "IOVER_ca2",
            "IIVER_ca1", "IOVER_ca3", "IIVER_ca2", "DGWER_ca", "CGWER_ca", "e_name", "number",
        ],
        "headers": [
            "编号", "污染物名称", "口摄入土壤颗粒物", "皮肤接触土壤颗粒物", "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物", "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物", "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物", "皮肤接触地下水", "饮用地下水",
        ],
        "displayColumns": [
            "ID", "p_name", "OISER_ca", "DCSER_ca", "PISER_ca", "IOVER_ca1", "IOVER_ca2",
            "IIVER_ca1", "IOVER_ca3", "IIVER_ca2", "DGWER_ca", "CGWER_ca",
        ],
    },
    {
        "table": "db_exposure_nc",
        "title": "暴露量-非致癌",
        "columns": [
            "ID", "p_name", "OISER_nc", "DCSER_nc", "PISER_nc", "IOVER_nc1", "IOVER_nc2",
            "IIVER_nc1", "IOVER_nc3", "IIVER_nc2", "DGWER_nc", "CGWER_nc", "e_name", "number",
        ],
        "headers": [
            "编号", "污染物名称", "口摄入土壤颗粒物", "皮肤接触土壤颗粒物", "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物", "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物", "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物", "皮肤接触地下水", "饮用地下水",
        ],
        "displayColumns": [
            "ID", "p_name", "OISER_nc", "DCSER_nc", "PISER_nc", "IOVER_nc1", "IOVER_nc2",
            "IIVER_nc1", "IOVER_nc3", "IIVER_nc2", "DGWER_nc", "CGWER_nc",
        ],
    },
    {
        "table": "db_cr",
        "title": "风险-致癌",
        "columns": [
            "ID", "p_name", "CR_ois", "CR_dcs", "CR_pis", "CR_iov1", "CR_iov2", "CR_iiv1",
            "CR_sn", "CR_iov3", "CR_iiv2", "CR_dgw", "CR_cgw", "CR_wn", "e_name", "number",
        ],
        "headers": [
            "编号", "污染物名称", "口摄入土壤颗粒物", "皮肤接触土壤颗粒物", "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物", "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物", "合计", "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物", "皮肤接触地下水", "饮用地下水", "合计",
        ],
        "displayColumns": [
            "ID", "p_name", "CR_ois", "CR_dcs", "CR_pis", "CR_iov1", "CR_iov2", "CR_iiv1",
            "CR_sn", "CR_iov3", "CR_iiv2", "CR_dgw", "CR_cgw", "CR_wn",
        ],
    },
    {
        "table": "db_hq",
        "title": "风险-危害商",
        "columns": [
            "ID", "p_name", "HQ_ois", "HQ_dcs", "HQ_pis", "HQ_iov1", "HQ_iov2", "HQ_iiv1",
            "HI_sn", "HQ_iov3", "HQ_iiv2", "HQ_dgw", "HQ_cgw", "HI_wn", "e_name", "number",
        ],
        "headers": [
            "编号", "污染物名称", "口摄入土壤颗粒物", "皮肤接触土壤颗粒物", "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物", "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物", "合计", "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物", "皮肤接触地下水", "饮用地下水", "合计",
        ],
        "displayColumns": [
            "ID", "p_name", "HQ_ois", "HQ_dcs", "HQ_pis", "HQ_iov1", "HQ_iov2", "HQ_iiv1",
            "HI_sn", "HQ_iov3", "HQ_iiv2", "HQ_dgw", "HQ_cgw", "HI_wn",
        ],
    },
    {
        "table": "db_pcr",
        "title": "贡献率-致癌",
        "columns": [
            "ID", "p_name", "PCR_ois", "PCR_dcs", "PCR_pis", "PCR_iov1", "PCR_iov2", "PCR_iiv1",
            "PCR_sn", "PCR_iov3", "PCR_iiv2", "PCR_dgw", "PCR_cgw", "PCR_wn", "e_name", "number",
        ],
        "headers": [
            "编号", "污染物名称", "口摄入土壤颗粒物", "皮肤接触土壤颗粒物", "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物", "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物", "合计", "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物", "皮肤接触地下水", "饮用地下水", "合计",
        ],
        "displayColumns": [
            "ID", "p_name", "PCR_ois", "PCR_dcs", "PCR_pis", "PCR_iov1", "PCR_iov2", "PCR_iiv1",
            "PCR_sn", "PCR_iov3", "PCR_iiv2", "PCR_dgw", "PCR_cgw", "PCR_wn",
        ],
    },
    {
        "table": "db_phq",
        "title": "贡献率-非致癌",
        "columns": [
            "ID", "p_name", "PHQ_ois", "PHQ_dcs", "PHQ_pis", "PHQ_iov1", "PHQ_iov2", "PHQ_iiv1",
            "PHI_sn", "PHQ_iov3", "PHQ_iiv2", "PHQ_dgw", "PHQ_cgw", "PHI_wn", "e_name", "number",
        ],
        "headers": [
            "编号", "污染物名称", "口摄入土壤颗粒物", "皮肤接触土壤颗粒物", "吸入土壤颗粒物",
            "吸入室外空气中来自表层土壤的气态污染物", "吸入室外空气中来自下层土壤的气态污染物",
            "吸入室内空气中来自下层土壤的气态污染物", "合计", "吸入室外空气中来自地下水的气态污染物",
            "吸入室内空气中来自地下水的气态污染物", "皮肤接触地下水", "饮用地下水", "合计",
        ],
        "displayColumns": [
            "ID", "p_name", "PHQ_ois", "PHQ_dcs", "PHQ_pis", "PHQ_iov1", "PHQ_iov2", "PHQ_iiv1",
            "PHI_sn", "PHQ_iov3", "PHQ_iiv2", "PHQ_dgw", "PHQ_cgw", "PHI_wn",
        ],
    },
    {
        "table": "db_cv",
        "title": "风险控制值",
        "columns": ["ID", "p_name", "RCVS_n", "HCVS_n", "RCVG_n", "HCVG_n", "CVS_pgw", "e_name", "number"],
        "headers": [
            "编号", "污染物名称", "土壤致癌风险控制值", "土壤非致癌风险控制值",
            "地下水致癌风险控制值", "地下水非致癌风险控制值", "保护地下水的土壤风险控制值",
        ],
        "displayColumns": ["ID", "p_name", "RCVS_n", "HCVS_n", "RCVG_n", "HCVG_n", "CVS_pgw"],
    },
]

POLLUTANT_FIELDS = (
    "id", "name", "english_name", "henry", "da", "dw", "koc", "solubility",
    "sfo", "iur", "rfdo", "rfc", "absgi", "absd", "saf", "kp",
)

# Excel 导入表头支持“一个字段多个别名”。
# 这样用户不必严格照搬某个模板，只要列名语义接近即可识别。
EXCEL_COLUMN_ALIASES = {
    "pollutant_id": ("编号", "污染物编号", "污染物id", "id", "number", "pollutant_id"),
    "name": ("污染物名称", "名称", "name", "p_name"),
    "english_name": ("英文名", "英文名称", "english_name", "e_name"),
    "surface_concentration": ("地表浓度", "表层土壤浓度", "surface_concentration"),
    "lower_soil_concentration": ("下层土壤浓度", "lower_soil_concentration"),
    "groundwater_concentration": ("地下水浓度", "groundwater_concentration"),
    "groundwater_protection_concentration": (
        "地下水保护浓度",
        "保护地下水浓度",
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
EXCEL_REQUIRED_IDENTIFIER_TEXT = "编号、污染物名称、英文名"
WORKSPACE_IMPORT_TEMPLATE_HEADERS = (
    "编号",
    "污染物名称",
    "英文名",
    "地表浓度",
    "下层土壤浓度",
    "地下水浓度",
    "地下水保护浓度",
)
WORKSPACE_IMPORT_TEMPLATE_NOTICE = (
    "使用说明：支持上传 .xlsx；至少填写“编号 / 污染物名称 / 英文名”其中之一；"
    "四类浓度留空按 0 处理；模板示例行可保留，导入时会自动忽略。"
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


def _normalize_header(text: str) -> str:
    """把 Excel 表头归一化，方便做别名匹配。

    例如：
    - `英文 名`
    - `english_name`
    - `English-Name`

    这些在归一化后都会更容易映射到同一个业务字段。
    """
    raw = str(text or "").strip().lower()
    return "".join(char for char in raw if char not in " \t\r\n_-()[]{}（）【】")


NORMALIZED_EXCEL_ALIAS_MAP = {
    _normalize_header(alias): field
    for field, aliases in EXCEL_COLUMN_ALIASES.items()
    for alias in aliases
}


def _json_value(value):
    """把 Decimal 等 Python 对象转换成 JSON 友好的值。"""
    if isinstance(value, Decimal):
        return float(value)
    return value


def serialize_pollutant(pollutant: Pollutant) -> dict[str, object]:
    """把污染物实体对象转成前端可读字典。"""
    return {field: _json_value(getattr(pollutant, field)) for field in POLLUTANT_FIELDS}


def serialize_selected(item) -> dict[str, object]:
    """把工作区中的聚合对象拆成前端可消费结构。

    注意这里同时保留了：
    - pollutant:     污染物基础属性
    - concentration: 当前工作区里的浓度

    这样前端在一个 payload 里就能拿到“这个污染物是什么”和“当前浓度是多少”。
    """
    return {
        "workspace_number": item.workspace_number,
        "pollutant": serialize_pollutant(item.pollutant),
        "concentration": {
            "workspace_number": item.concentration.workspace_number,
            "pollutant_id": item.concentration.pollutant_id,
            "name": item.concentration.name,
            "english_name": item.concentration.english_name,
            "surface_concentration": _json_value(item.concentration.surface_concentration),
            "lower_soil_concentration": _json_value(item.concentration.lower_soil_concentration),
            "groundwater_concentration": _json_value(item.concentration.groundwater_concentration),
            "groundwater_protection_concentration": _json_value(
                item.concentration.groundwater_protection_concentration
            ),
        },
    }


def serialize_parameter_group(group_id: int, rows: list[ParameterRow]) -> dict[str, object]:
    """把某一组参数整理成参数弹窗需要的格式。"""
    return {
        "id": group_id,
        "title": PARAMETER_GROUPS[group_id],
        "rows": [
            {
                "name": row.name,
                "label": row.label,
                "data_gi": _json_value(row.data_gi),
                "data_gii": _json_value(row.data_gii),
                "data_zi": _json_value(row.data_zi),
                "data_zii": _json_value(row.data_zii),
                "group_id": row.group_id,
            }
            for row in rows
        ],
    }


def format_result_value(value):
    """把结果值格式化成前端展示文本。

    大部分风险结果是非常小的数字，直接展示原始浮点数可读性很差，
    因此这里统一转为科学计数法。
    """
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        return f"{value:.2e}"
    return value


def serialize_results(result_repository: ResultRepository) -> list[dict[str, object]]:
    """把数据库中的结果表转换为前端标签页数据。"""
    tables: list[dict[str, object]] = []
    for config in RESULT_CONFIGS:
        raw_rows = result_repository.fetch_table(config["table"])
        rows = [dict(zip(config["columns"], row)) for row in raw_rows]
        tables.append(
            {
                "key": config["table"],
                "title": config["title"],
                "headers": config["headers"],
                "rows": [
                    [format_result_value(row[column]) for column in config["displayColumns"]]
                    for row in rows
                ],
            }
        )
    return tables


def build_export_rows(result_repository: ResultRepository) -> list[list[str]]:
    """把结果表铺平成适合导出 Excel 的二维数组。"""
    rows: list[list[str]] = []
    for table in serialize_results(result_repository):
        rows.append([table["title"]])
        rows.append(table["headers"])
        rows.extend([[str(cell) for cell in row] for row in table["rows"]])
        rows.append([])
    return rows


class RiskBackend:
    """后端业务门面。

    这是 HTTP 请求真正调用的业务对象。它把多个仓储和服务组装起来，
    对外暴露的是“面向界面动作”的方法，例如：
    - list_catalog
    - add_workspace_item
    - calculate
    - export_results

    因此前端无需知道数据库细节，只需命中对应接口即可。
    """

    def __init__(self):
        # 确保运行库数据库存在是整个后端的第一步。
        # 首次运行时，这里会把模板数据库复制到本地应用目录。
        ensure_database()
        self.catalog_repository = CatalogRepository()
        self.workspace_repository = WorkspaceRepository()
        self.parameter_repository = ParameterRepository()
        self.result_repository = ResultRepository()
        self.auth_repository = AuthRepository()
        self.calculator = RiskCalculator(self.parameter_repository)

    def health(self) -> dict[str, object]:
        """健康检查接口。

        除了告诉前端“后端在线”，还会顺手带上：
        - 当前运行数据库路径
        - 污染物总数
        - 工作区污染物总数

        这样前端首页的指标卡就能一次性拿到所需信息。
        这里特意使用 count 查询，而不是把整张目录或整张工作区读出来，
        因为健康检查是高频轻量接口，不适合做全量扫描。
        """
        return {
            "status": "ok",
            "database": str(Path(RUNTIME_DB)),
            "catalog_count": self.catalog_repository.count_pollutants(),
            "workspace_count": self.workspace_repository.count_selected_pollutants(),
        }

    def list_catalog(self, keyword: str) -> dict[str, object]:
        """查询污染物目录。"""
        rows = self.catalog_repository.list_pollutants(keyword)
        return {"items": [serialize_pollutant(row) for row in rows], "total": len(rows)}

    def list_workspace(self) -> dict[str, object]:
        """列出当前工作区。"""
        rows = self.workspace_repository.list_selected_pollutants()
        return {"items": [serialize_selected(row) for row in rows], "total": len(rows)}

    def add_workspace_item(self, pollutant_id: int) -> dict[str, object]:
        """把目录中的某个污染物加入工作区。

        这里返回的是“新增项 + 总数”，而不是整张工作区。
        这样当前端连续添加上百条污染物时，
        就不会因为每次都回传整张工作区而产生明显性能损耗。
        """
        pollutant = self.catalog_repository.get_pollutant(pollutant_id)
        if pollutant is None:
            raise ValueError("未找到对应污染物")
        workspace_number = self.workspace_repository.add_pollutant(pollutant)
        item = SelectedPollutant(
            workspace_number=workspace_number,
            pollutant=pollutant,
            concentration=PollutantConcentration(
                workspace_number=workspace_number,
                pollutant_id=pollutant.id,
                name=pollutant.name,
                english_name=pollutant.english_name,
                surface_concentration=Decimal("0"),
                lower_soil_concentration=Decimal("0"),
                groundwater_concentration=Decimal("0"),
                groundwater_protection_concentration=Decimal("0"),
            ),
        )
        return {
            "item": serialize_selected(item),
            "added_workspace_number": workspace_number,
            "total": self.workspace_repository.count_selected_pollutants(),
        }

    def import_workspace_excel(self, content: bytes) -> dict[str, object]:
        """从 Excel 中批量导入污染物和浓度。

        这条链路服务的业务场景是：
        - 用户已经在外部 Excel 里整理好了污染物清单
        - 希望一次性把“污染物 + 四类浓度”直接带进工作区

        这里故意只支持 `.xlsx`，并且采用项目内置的轻量解析器，
        目的是避免为了一个导入功能重新引入更重的第三方库。
        """
        if not content:
            raise ValueError("上传的 Excel 文件为空")

        rows = load_xlsx_rows(content)
        header_row_index, column_map = self._parse_excel_columns(rows)
        imported_entries: list[dict[str, object]] = []
        errors: list[str] = []

        for row_number, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
            if self._is_excel_example_row(row):
                continue
            if not any(str(cell).strip() for cell in row):
                continue
            try:
                pollutant = self._resolve_excel_pollutant(column_map, row, row_number)
                imported_entries.append(
                    {
                        "pollutant": pollutant,
                        "surface_concentration": self._parse_excel_decimal(
                            self._excel_cell(row, column_map, "surface_concentration"),
                            "地表浓度",
                            row_number,
                        ),
                        "lower_soil_concentration": self._parse_excel_decimal(
                            self._excel_cell(row, column_map, "lower_soil_concentration"),
                            "下层土壤浓度",
                            row_number,
                        ),
                        "groundwater_concentration": self._parse_excel_decimal(
                            self._excel_cell(row, column_map, "groundwater_concentration"),
                            "地下水浓度",
                            row_number,
                        ),
                        "groundwater_protection_concentration": self._parse_excel_decimal(
                            self._excel_cell(row, column_map, "groundwater_protection_concentration"),
                            "地下水保护浓度",
                            row_number,
                        ),
                    }
                )
            except ValueError as exc:
                errors.append(f"第 {row_number} 行：{exc}")

        if errors:
            more = "；其余错误请修正后重试" if len(errors) > 5 else ""
            raise ValueError("Excel 导入失败：" + "；".join(errors[:5]) + more)
        if not imported_entries:
            raise ValueError("Excel 中没有可导入的数据行")

        imported_items = self.workspace_repository.import_pollutants(imported_entries)
        return {
            "items": [serialize_selected(item) for item in imported_items],
            "imported": len(imported_items),
            "total": self.workspace_repository.count_selected_pollutants(),
        }

    def export_workspace_import_template(self) -> bytes:
        """导出工作区 Excel 导入模板。

        模板里会直接带上：
        - 一行使用说明
        - 一行正式表头
        - 一行示例数据

        这样用户下载后基本不需要猜字段格式，照着填就能导入。
        """
        return build_xlsx(
            [
                [WORKSPACE_IMPORT_TEMPLATE_NOTICE],
                list(WORKSPACE_IMPORT_TEMPLATE_HEADERS),
                list(WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_ROW),
                [],
            ]
        )

    def remove_workspace_item(self, workspace_number: int) -> dict[str, object]:
        """移除工作区中的一行。"""
        self.workspace_repository.remove_workspace_row(workspace_number)
        return self.list_workspace()

    def reset_workspace(self) -> dict[str, object]:
        """清空工作区，并重置结果表。"""
        self.workspace_repository.clear_workspace()
        self.result_repository.reset()
        return self.list_workspace()

    def update_concentrations(self, payload_items: list[dict[str, object]]) -> dict[str, object]:
        """保存前端提交的浓度草稿。"""
        items = [
            PollutantConcentration(
                workspace_number=int(item["workspace_number"]),
                pollutant_id=int(item["pollutant_id"]),
                name=str(item.get("name", "")),
                english_name=str(item.get("english_name", "")),
                surface_concentration=Decimal(str(item.get("surface_concentration", 0))),
                lower_soil_concentration=Decimal(str(item.get("lower_soil_concentration", 0))),
                groundwater_concentration=Decimal(str(item.get("groundwater_concentration", 0))),
                groundwater_protection_concentration=Decimal(
                    str(item.get("groundwater_protection_concentration", 0))
                ),
            )
            for item in payload_items
        ]
        self.workspace_repository.update_concentrations(items)
        return self.list_workspace()

    def list_parameters(self) -> dict[str, object]:
        """列出四组参数模板。"""
        return {
            "groups": [
                serialize_parameter_group(group_id, self.parameter_repository.list_group_rows(group_id))
                for group_id in PARAMETER_GROUPS
            ]
        }

    def reset_parameters(self) -> dict[str, object]:
        """恢复默认参数。"""
        self.parameter_repository.reset_defaults()
        return self.list_parameters()

    def save_parameters(self, groups: list[dict[str, object]]) -> dict[str, object]:
        """保存参数弹窗中的所有组。"""
        for group in groups:
            rows = [
                ParameterRow(
                    name=str(row["name"]),
                    label=str(row.get("label", row["name"])),
                    data_gi=Decimal(str(row.get("data_gi", 0))),
                    data_gii=Decimal(str(row.get("data_gii", 0))),
                    data_zi=Decimal(str(row.get("data_zi", 0))),
                    data_zii=Decimal(str(row.get("data_zii", 0))),
                    group_id=int(group["id"]),
                )
                for row in group.get("rows", [])
            ]
            self.parameter_repository.save_group_rows(rows)
        return self.list_parameters()

    def calculate(self, payload: dict[str, object]) -> dict[str, object]:
        """执行风险计算主流程。

        这条链路是项目最核心的一步：
        1. 读取工作区污染物和浓度。
        2. 校验是否至少选了一条暴露途径。
        3. 构造场地选择条件（标准 + 用地类型）。
        4. 交给 RiskCalculator 执行公式计算。
        5. 把每条工作区结果写回各张结果表。
        6. 再把结果表序列化返回给前端。
        """
        selected = self.workspace_repository.list_selected_pollutants()
        if not selected:
            raise ValueError("请先把污染物加入工作区")
        pathways = {key: bool(payload.get("pathways", {}).get(key)) for key in PATHWAY_LABELS}
        if not any(pathways.values()):
            raise ValueError("请至少选择一个暴露途径")
        selection = SiteSelection(
            standard=str(payload.get("standard", "G")),
            area_type=str(payload.get("area_type", "I")),
        )
        self.result_repository.reset()
        results = self.calculator.calculate(selection, selected, pathways)
        for workspace_number, table_values in results.items():
            for table_name, values in table_values.items():
                self.result_repository.update_table(table_name, workspace_number, values)
        return {"tables": serialize_results(self.result_repository)}

    def list_results(self) -> dict[str, object]:
        """读取当前结果表。"""
        return {"tables": serialize_results(self.result_repository)}

    def export_results(self) -> bytes:
        """导出当前结果为 Excel 二进制内容。"""
        return build_xlsx(build_export_rows(self.result_repository))

    def login(self, payload: dict[str, object]) -> dict[str, object]:
        """管理员登录校验。"""
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not username or not password:
            raise ValueError("用户名和密码不能为空")
        success = self.auth_repository.validate(username, password)
        return {"success": success, "username": username if success else ""}

    def update_password(self, payload: dict[str, object]) -> dict[str, object]:
        """管理员修改密码。"""
        username = str(payload.get("username", "")).strip()
        old_password = str(payload.get("old_password", "")).strip()
        new_password = str(payload.get("new_password", "")).strip()
        if not username or not old_password or not new_password:
            raise ValueError("用户名、原密码和新密码不能为空")
        if not self.auth_repository.validate(username, old_password):
            raise ValueError("原密码输入错误")
        updated = self.auth_repository.update_password(username, new_password)
        return {"success": updated > 0}

    def add_pollutant(self, payload: dict[str, object]) -> dict[str, object]:
        """新增污染物目录条目。"""
        pollutant = self._build_pollutant(payload)
        if not pollutant.name:
            raise ValueError("污染物名称不能为空")
        self.catalog_repository.add_pollutant(pollutant)
        return self.list_catalog(str(payload.get("keyword", "")))

    def update_pollutant(self, pollutant_id: int, payload: dict[str, object]) -> dict[str, object]:
        """更新目录中的某个污染物。"""
        pollutant = self._build_pollutant(payload, pollutant_id)
        self.catalog_repository.update_pollutant(pollutant)
        return self.list_catalog(str(payload.get("keyword", "")))

    def delete_pollutant(self, pollutant_id: int, keyword: str) -> dict[str, object]:
        """删除污染物并返回当前查询结果。"""
        self.catalog_repository.delete_pollutant(pollutant_id)
        return self.list_catalog(keyword)

    def _build_pollutant(self, payload: dict[str, object], pollutant_id: int = 0) -> Pollutant:
        """把前端提交的表单数据组装成 Pollutant 实体。"""
        return Pollutant(
            id=pollutant_id,
            name=str(payload.get("name", "")).strip(),
            english_name=str(payload.get("english_name", "")).strip(),
            henry=Decimal(str(payload.get("henry", 0))),
            da=Decimal(str(payload.get("da", 0))),
            dw=Decimal(str(payload.get("dw", 0))),
            koc=Decimal(str(payload.get("koc", 0))),
            solubility=Decimal(str(payload.get("solubility", 0))),
            sfo=Decimal(str(payload.get("sfo", 0))),
            iur=Decimal(str(payload.get("iur", 0))),
            rfdo=Decimal(str(payload.get("rfdo", 0))),
            rfc=Decimal(str(payload.get("rfc", 0))),
            absgi=Decimal(str(payload.get("absgi", 0))),
            absd=Decimal(str(payload.get("absd", 0))),
            saf=Decimal(str(payload.get("saf", 1))),
            kp=Decimal(str(payload.get("kp", 0))),
        )

    def _parse_excel_columns(self, rows: list[list[str]]) -> tuple[int, dict[str, int]]:
        """从 Excel 中识别表头，并映射成后端字段名。

        返回值中的第一个数字是“表头所在行的 0 基索引”。
        这样既便于代码里继续切片，又能通过 `+ 1` 很容易换算回用户看到的 Excel 行号。
        """
        for row_index, row in enumerate(rows):
            row_number = row_index + 1
            normalized_headers = {
                NORMALIZED_EXCEL_ALIAS_MAP[_normalize_header(cell)]: index
                for index, cell in enumerate(row)
                if _normalize_header(cell) in NORMALIZED_EXCEL_ALIAS_MAP
            }
            if not normalized_headers:
                continue
            if not any(field in normalized_headers for field in EXCEL_IDENTIFIER_FIELDS):
                raise ValueError(f"第 {row_number} 行缺少标识列，至少需要 {EXCEL_REQUIRED_IDENTIFIER_TEXT} 之一")
            return row_index, normalized_headers
        raise ValueError(f"未识别到可用表头，至少需要 {EXCEL_REQUIRED_IDENTIFIER_TEXT} 之一")

    def _excel_cell(self, row: list[str], column_map: dict[str, int], field: str) -> str:
        """安全读取 Excel 某一列的文本值。"""
        column_index = column_map.get(field)
        if column_index is None or column_index >= len(row):
            return ""
        return str(row[column_index]).strip()

    def _is_excel_example_row(self, row: list[str]) -> bool:
        """判断当前行是否为模板自带的示例行。

        用户拿着模板直接录入时，最常见的误操作之一是：
        “忘了删除示例行”。

        这里主动做一次识别，可以让示例继续保留在文件里，
        又不会被真的导入到工作区。
        """
        return any(str(cell).strip() == WORKSPACE_IMPORT_TEMPLATE_EXAMPLE_MARKER for cell in row)

    def _parse_excel_decimal(self, value: str, label: str, row_number: int) -> Decimal:
        """把 Excel 中的浓度文本转成 Decimal。

        浓度列留空会按 0 处理；
        只有在用户明确填了非法文本时才报错。
        """
        if value == "":
            return Decimal("0")
        try:
            return Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{label} 不是合法数字（当前值：{value}）") from None

    def _parse_excel_pollutant_id(self, value: str) -> int | None:
        """把 Excel 中的污染物编号解析为整数。

        Excel 常把整数显示成 `23` 或 `23.0`，这里两种都接受。
        """
        if value == "":
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError(f"污染物编号不是合法数字（当前值：{value}）") from None
        if parsed != parsed.to_integral_value():
            raise ValueError(f"污染物编号必须是整数（当前值：{value}）")
        return int(parsed)

    def _resolve_excel_pollutant(
        self,
        column_map: dict[str, int],
        row: list[str],
        row_number: int,
    ) -> Pollutant:
        """根据 Excel 行里的标识列找到目录中的污染物。

        允许三种定位方式：
        - 编号
        - 中文名（支持一定程度的模糊匹配，例如“砷”匹配“砷（无机）”）
        - 英文名

        如果同时提供多种标识，但它们指向不同污染物，也会及时报错，
        避免把错误数据悄悄导入工作区。
        """
        raw_id = self._excel_cell(row, column_map, "pollutant_id")
        raw_name = self._excel_cell(row, column_map, "name")
        raw_english_name = self._excel_cell(row, column_map, "english_name")

        pollutant: Pollutant | None = None
        pollutant_id = self._parse_excel_pollutant_id(raw_id)
        if pollutant_id is not None:
            pollutant = self.catalog_repository.get_pollutant(pollutant_id)
            if pollutant is None:
                raise ValueError(f"未找到编号为 {pollutant_id} 的污染物")

        if raw_name:
            by_name = self.catalog_repository.find_by_name(raw_name)
            if by_name is None:
                raise ValueError(f"未找到名称为“{raw_name}”的污染物")
            if pollutant and pollutant.id != by_name.id:
                raise ValueError("编号和污染物名称对应的不是同一条目录记录")
            pollutant = by_name

        if raw_english_name:
            by_english_name = self.catalog_repository.find_by_english_name(raw_english_name)
            if by_english_name is None:
                raise ValueError(f"未找到英文名为“{raw_english_name}”的污染物")
            if pollutant and pollutant.id != by_english_name.id:
                raise ValueError("编号/名称和英文名对应的不是同一条目录记录")
            pollutant = by_english_name

        if pollutant is None:
            raise ValueError(f"至少需要填写 {EXCEL_REQUIRED_IDENTIFIER_TEXT} 之一")
        return pollutant


class RequestHandler(BaseHTTPRequestHandler):
    """最薄的一层 HTTP 路由处理器。

    BaseHTTPRequestHandler 不像 FastAPI/Flask 那样自带路由系统，
    所以这里用最直接的 if/else 分发请求。

    教学上可以重点观察：
    - do_GET / do_POST / do_PUT / do_DELETE 各自对应什么操作
    - RequestHandler 不做业务细节，只负责收发 HTTP 数据
    """

    backend = RiskBackend()

    def do_OPTIONS(self) -> None:
        # 处理浏览器和 WebView 的预检请求。
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """只读接口：健康检查、目录、工作区、参数、结果。"""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path == "/api/health":
                self._send_json(self.backend.health())
                return
            if parsed.path == "/api/catalog":
                self._send_json(self.backend.list_catalog(_first_query(params, "keyword")))
                return
            if parsed.path == "/api/workspace":
                self._send_json(self.backend.list_workspace())
                return
            if parsed.path == "/api/workspace/import-template":
                self._send_binary(
                    self.backend.export_workspace_import_template(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "污染物导入模板.xlsx",
                )
                return
            if parsed.path == "/api/parameters":
                self._send_json(self.backend.list_parameters())
                return
            if parsed.path == "/api/results":
                self._send_json(self.backend.list_results())
                return
            self._send_error("未找到接口", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(str(exc))

    def do_POST(self) -> None:
        """创建型或动作型接口。"""
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/workspace/import-excel":
                self._send_json(self.backend.import_workspace_excel(self._read_body()))
                return
            payload = self._read_json()
            if parsed.path == "/api/workspace/add":
                self._send_json(self.backend.add_workspace_item(int(payload["pollutant_id"])))
                return
            if parsed.path == "/api/workspace/reset":
                self._send_json(self.backend.reset_workspace())
                return
            if parsed.path == "/api/parameters/reset":
                self._send_json(self.backend.reset_parameters())
                return
            if parsed.path == "/api/calculate":
                self._send_json(self.backend.calculate(payload))
                return
            if parsed.path == "/api/results/export":
                self._send_binary(
                    self.backend.export_results(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "risk-results.xlsx",
                )
                return
            if parsed.path == "/api/auth/login":
                self._send_json(self.backend.login(payload))
                return
            if parsed.path == "/api/auth/password":
                self._send_json(self.backend.update_password(payload))
                return
            if parsed.path == "/api/admin/pollutants":
                self._send_json(self.backend.add_pollutant(payload))
                return
            self._send_error("未找到接口", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(str(exc))

    def do_PUT(self) -> None:
        """更新型接口。"""
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/workspace/concentrations":
                self._send_json(self.backend.update_concentrations(payload.get("items", [])))
                return
            if parsed.path == "/api/parameters":
                self._send_json(self.backend.save_parameters(payload.get("groups", [])))
                return
            if parsed.path.startswith("/api/admin/pollutants/"):
                pollutant_id = int(parsed.path.rsplit("/", 1)[-1])
                self._send_json(self.backend.update_pollutant(pollutant_id, payload))
                return
            self._send_error("未找到接口", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(str(exc))

    def do_DELETE(self) -> None:
        """删除型接口。"""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path.startswith("/api/workspace/"):
                workspace_number = int(parsed.path.rsplit("/", 1)[-1])
                self._send_json(self.backend.remove_workspace_item(workspace_number))
                return
            if parsed.path.startswith("/api/admin/pollutants/"):
                pollutant_id = int(parsed.path.rsplit("/", 1)[-1])
                self._send_json(self.backend.delete_pollutant(pollutant_id, _first_query(params, "keyword")))
                return
            self._send_error("未找到接口", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(str(exc))

    def log_message(self, format: str, *args) -> None:
        # 关闭 http.server 默认日志，避免桌面端启动时刷屏。
        return

    def _read_json(self) -> dict[str, object]:
        """把请求体读成 JSON 对象。"""
        raw = self._read_body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _read_body(self) -> bytes:
        """按原样读取请求体。

        之所以单独抽出来，是因为现在除了 JSON 之外，
        还新增了 Excel 二进制上传这类“原始字节流”场景。
        """
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return b""
        return self.rfile.read(content_length)

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        """发送 JSON 响应。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_binary(self, payload: bytes, content_type: str, filename: str) -> None:
        """发送二进制响应，用于 Excel 导出。"""
        ascii_filename = filename.encode("ascii", "ignore").decode("ascii").strip() or "download.bin"
        encoded_filename = quote(filename)
        self.send_response(HTTPStatus.OK)
        self._write_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}",
        )
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        """统一错误出口。"""
        self._send_json({"error": message}, status=status)

    def _write_cors_headers(self) -> None:
        # 当前桌面端和浏览器调试都走本地请求，因此这里统一开放本地跨域。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")


def _first_query(params: dict[str, list[str]], key: str) -> str:
    """从 parse_qs 结果中安全取第一个查询参数值。"""
    values = params.get(key)
    return values[0] if values else ""


def run(host: str = "127.0.0.1", port: int = 38911) -> None:
    """启动线程化 HTTP 服务。"""
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"risk-backend listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    """命令行入口，供桌面壳或开发时直接调用。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=38911)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
