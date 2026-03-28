from __future__ import annotations

import argparse
import json
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from risk_backend.exporters import build_xlsx
from risk_backend.models.entities import ParameterRow, Pollutant, PollutantConcentration, SiteSelection
from risk_backend.repositories.auth import AuthRepository
from risk_backend.repositories.catalog import CatalogRepository
from risk_backend.repositories.database import RUNTIME_DB, ensure_database
from risk_backend.repositories.parameters import PARAMETER_GROUPS, ParameterRepository
from risk_backend.repositories.results import ResultRepository
from risk_backend.repositories.workspace import WorkspaceRepository
from risk_backend.services.calculator import RiskCalculator


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
        """
        return {
            "status": "ok",
            "database": str(Path(RUNTIME_DB)),
            "catalog_count": len(self.catalog_repository.list_pollutants("")),
            "workspace_count": len(self.workspace_repository.list_selected_pollutants()),
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
        """把目录中的某个污染物加入工作区。"""
        pollutant = self.catalog_repository.get_pollutant(pollutant_id)
        if pollutant is None:
            raise ValueError("未找到对应污染物")
        workspace_number = self.workspace_repository.add_pollutant(pollutant)
        payload = self.list_workspace()
        payload["added_workspace_number"] = workspace_number
        return payload

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
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

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
        self.send_response(HTTPStatus.OK)
        self._write_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
