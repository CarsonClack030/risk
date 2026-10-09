"""Application service used by the HTTP transport layer."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from decimal import Decimal, InvalidOperation

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
from risk_backend.repositories.database import (
    RUNTIME_DB,
    ensure_database,
    export_project_database,
    read_project_metadata,
    replace_runtime_database,
    write_project_metadata,
)
from risk_backend.repositories.operation_logs import OperationLogRepository
from risk_backend.repositories.parameters import (
    PARAMETER_GROUPS,
    PARAMETER_NAMES,
    PARAMETER_UNITS,
    ParameterRepository,
)
from risk_backend.repositories.results import ResultRepository
from risk_backend.repositories.workspace import WorkspaceRepository
from risk_backend.serialization import (
    build_export_rows,
    serialize_parameter_group,
    serialize_pollutant,
    serialize_results,
    serialize_selected,
)
from risk_backend.services.calculator import RiskCalculator
from risk_backend.workspace_import import WorkspaceImporter

PATHWAY_KEYS = (
    "ois",
    "dcs",
    "pis",
    "dgw",
    "cgw",
    "iov3",
    "iiv2",
    "iov1",
    "iov2",
    "iiv1",
)

POLLUTANT_DECIMAL_FIELDS = {
    "henry": ("Henry", "0"),
    "da": ("Da", "0"),
    "dw": ("Dw", "0"),
    "koc": ("Koc", "0"),
    "solubility": ("S", "0"),
    "sfo": ("SFo", "0"),
    "iur": ("IUR", "0"),
    "rfdo": ("RfDo", "0"),
    "rfc": ("RfC", "0"),
    "absgi": ("ABSgi", "0"),
    "absd": ("ABSd", "0"),
    "saf": ("SAF", "1"),
    "kp": ("Kp", "0"),
}
ADMIN_SESSION_SECONDS = 8 * 60 * 60
MAX_WORKSPACE_ITEMS = 10_000
MAX_TEXT_FIELD_LENGTH = 256
LOGGER = logging.getLogger("risk_backend.application")

PARAMETER_VALUE_COLUMNS = (
    ("data_gi", "国家标准·第一类用地"),
    ("data_gii", "国家标准·第二类用地"),
    ("data_zi", "浙江标准·第一类用地"),
    ("data_zii", "浙江标准·第二类用地"),
)


class RiskBackend:
    """Expose use-case methods without coupling them to HTTP details."""

    def __init__(self) -> None:
        ensure_database()
        self.catalog_repository = CatalogRepository()
        self.workspace_repository = WorkspaceRepository()
        self.parameter_repository = ParameterRepository()
        self.result_repository = ResultRepository()
        self.operation_log_repository = OperationLogRepository()
        self.auth_repository = AuthRepository()
        self.calculator = RiskCalculator(self.parameter_repository)
        self.workspace_importer = WorkspaceImporter(
            self.catalog_repository,
            self.workspace_repository,
        )
        self._admin_sessions: dict[str, tuple[str, float]] = {}
        self._session_lock = threading.Lock()
        # 新建项目会同时清空工作区、恢复参数并重置日志。
        # Windows 下用户快速双击按钮时，两个请求并发写 SQLite 容易触发锁错误，
        # 因此把整个项目切换过程串行化。
        self._project_lock = threading.Lock()

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "database": str(RUNTIME_DB),
            "catalog_count": self.catalog_repository.count_pollutants(),
            "workspace_count": self.workspace_repository.count_selected_pollutants(),
            "project": read_project_metadata(),
        }

    def record_operation(
        self,
        *,
        level: str,
        action: str,
        message: str,
        details: str = "",
        change_details: str = "",
    ) -> None:
        """写入日志，但不让日志故障反过来阻断业务操作。"""
        # 某些单元测试会用 __new__ 构造一个只测试计算事务的精简对象，
        # 这类对象没有初始化日志仓库时应继续保持原有测试行为。
        if not hasattr(self, "operation_log_repository"):
            return
        try:
            self.operation_log_repository.append(
                level=level,
                action=action,
                message=message,
                details=details,
                change_details=change_details,
            )
        except Exception:
            LOGGER.exception("Failed to write operation log")

    def list_operation_logs(self, limit: int | None = None) -> dict[str, object]:
        return {"items": self.operation_log_repository.list_recent(limit)}

    def export_operation_logs(self) -> bytes:
        self.record_operation(
            level="info",
            action="操作日志",
            message="导出了操作日志",
        )
        return self.operation_log_repository.export_csv()

    def list_catalog(self, keyword: str) -> dict[str, object]:
        rows = self.catalog_repository.list_pollutants(keyword)
        return {"items": [serialize_pollutant(row) for row in rows], "total": len(rows)}

    def list_workspace(self) -> dict[str, object]:
        rows = self.workspace_repository.list_selected_pollutants()
        return {"items": [serialize_selected(row) for row in rows], "total": len(rows)}

    def add_workspace_item(self, pollutant_id: int) -> dict[str, object]:
        pollutant = self.catalog_repository.get_pollutant(pollutant_id)
        if pollutant is None:
            raise ValueError("未找到对应污染物")

        workspace_number = self.workspace_repository.add_pollutant(pollutant)
        concentration = PollutantConcentration(
            workspace_number=workspace_number,
            pollutant_id=pollutant.id,
            name=pollutant.name,
            english_name=pollutant.english_name,
            surface_concentration=Decimal("0"),
            lower_soil_concentration=Decimal("0"),
            groundwater_concentration=Decimal("0"),
            groundwater_protection_concentration=Decimal("0"),
        )
        item = SelectedPollutant(workspace_number, pollutant, concentration)
        self.record_operation(
            level="info",
            action="工作区",
            message=f"添加污染物：{pollutant.name}",
            details=f"工作区序号：{workspace_number}，污染物编号：{pollutant.id}",
        )
        return {
            "item": serialize_selected(item),
            "added_workspace_number": workspace_number,
            "total": self.workspace_repository.count_selected_pollutants(),
        }

    def import_workspace_file(
        self,
        content: bytes,
        *,
        filename: str = "",
        content_type: str = "",
    ) -> dict[str, object]:
        result = self.workspace_importer.import_file(
            content,
            filename=filename,
            content_type=content_type,
        )
        self.record_operation(
            level="info",
            action="工作区导入",
            message=f"从 {filename or '文件'} 导入污染物",
            details=f"导入数量：{result.get('imported', len(result.get('items', [])))}",
        )
        return result

    def export_workspace_import_template(self) -> bytes:
        self.record_operation(
            level="info",
            action="文件导出",
            message="导出了污染物导入模板",
        )
        return self.workspace_importer.build_template()

    def remove_workspace_item(self, workspace_number: int) -> dict[str, object]:
        self.workspace_repository.remove_workspace_row(workspace_number)
        self.record_operation(
            level="info",
            action="工作区",
            message=f"移除了工作区序号：{workspace_number}",
        )
        return self.list_workspace()

    def reset_workspace(self) -> dict[str, object]:
        self.workspace_repository.clear_workspace()
        self.record_operation(
            level="info",
            action="工作区",
            message="重置了工作区",
        )
        return self.list_workspace()

    def update_concentrations(
        self, payload_items: list[dict[str, object]]
    ) -> dict[str, object]:
        if not isinstance(payload_items, list):
            raise ValueError("浓度数据必须是列表")
        if len(payload_items) > MAX_WORKSPACE_ITEMS:
            raise ValueError(f"工作区条目不能超过 {MAX_WORKSPACE_ITEMS} 条")

        items: list[PollutantConcentration] = []
        workspace_numbers: set[int] = set()
        for index, raw_item in enumerate(payload_items, start=1):
            if not isinstance(raw_item, dict):
                raise ValueError(f"第 {index} 条浓度数据格式错误")
            workspace_number = self._parse_positive_integer(
                raw_item.get("workspace_number"), f"第 {index} 条工作区序号"
            )
            pollutant_id = self._parse_positive_integer(
                raw_item.get("pollutant_id"), f"第 {index} 条污染物编号"
            )
            if workspace_number in workspace_numbers:
                raise ValueError(f"工作区序号 {workspace_number} 重复")
            workspace_numbers.add(workspace_number)
            items.append(
                PollutantConcentration(
                    workspace_number=workspace_number,
                    pollutant_id=pollutant_id,
                    name=str(raw_item.get("name", "")),
                    english_name=str(raw_item.get("english_name", "")),
                    surface_concentration=self._parse_non_negative_decimal(
                        raw_item.get("surface_concentration", 0),
                        f"第 {index} 条地表浓度",
                    ),
                    lower_soil_concentration=self._parse_non_negative_decimal(
                        raw_item.get("lower_soil_concentration", 0),
                        f"第 {index} 条下层土壤浓度",
                    ),
                    groundwater_concentration=self._parse_non_negative_decimal(
                        raw_item.get("groundwater_concentration", 0),
                        f"第 {index} 条地下水浓度",
                    ),
                    groundwater_protection_concentration=self._parse_non_negative_decimal(
                        raw_item.get("groundwater_protection_concentration", 0),
                        f"第 {index} 条地下水保护浓度",
                    ),
                )
            )
        self.workspace_repository.update_concentrations(items)
        self.record_operation(
            level="info",
            action="浓度设置",
            message="更新了污染物浓度",
            details=f"更新数量：{len(items)}",
        )
        return self.list_workspace()

    def list_parameters(self) -> dict[str, object]:
        return {
            "groups": [
                serialize_parameter_group(
                    group_id,
                    self.parameter_repository.list_group_rows(group_id),
                )
                for group_id in PARAMETER_GROUPS
            ]
        }

    def reset_parameters(self) -> dict[str, object]:
        before = self._parameter_snapshot()
        self.parameter_repository.reset_defaults()
        after = self._parameter_snapshot()
        changed = self._record_parameter_changes(before, after, "恢复默认")
        if not changed:
            self.record_operation(
                level="info",
                action="参数设置",
                message="恢复了默认参数（没有数值变化）",
            )
        return self.list_parameters()

    def save_parameters(self, groups: list[dict[str, object]]) -> dict[str, object]:
        if not isinstance(groups, list):
            raise ValueError("参数分组必须是列表")
        parsed_rows: list[ParameterRow] = []
        seen_parameter_names: set[str] = set()
        for group_index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                raise ValueError(f"第 {group_index} 个参数分组格式错误")
            group_id = self._parse_positive_integer(
                group.get("id"), f"第 {group_index} 个参数分组编号"
            )
            if group_id not in PARAMETER_GROUPS:
                raise ValueError(f"不支持的参数分组：{group_id}")
            raw_rows = group.get("rows", [])
            if not isinstance(raw_rows, list):
                raise ValueError(f"参数分组 {group_id} 的 rows 必须是列表")
            for row_index, row in enumerate(raw_rows, start=1):
                if not isinstance(row, dict):
                    raise ValueError(f"参数分组 {group_id} 第 {row_index} 行格式错误")
                name = str(row.get("name", "")).strip()
                if name not in PARAMETER_NAMES:
                    raise ValueError(f"不支持的参数：{name}")
                if name in seen_parameter_names:
                    raise ValueError(f"参数 {name} 重复提交")
                seen_parameter_names.add(name)
                label = str(row.get("label", name))
                parsed_rows.append(
                    ParameterRow(
                        name=name,
                        label=label,
                        unit=PARAMETER_UNITS[name],
                        data_gi=self._parse_parameter_decimal(
                            row.get("data_gi"), label, "国家标准·第一类用地"
                        ),
                        data_gii=self._parse_parameter_decimal(
                            row.get("data_gii"), label, "国家标准·第二类用地"
                        ),
                        data_zi=self._parse_parameter_decimal(
                            row.get("data_zi"), label, "浙江标准·第一类用地"
                        ),
                        data_zii=self._parse_parameter_decimal(
                            row.get("data_zii"), label, "浙江标准·第二类用地"
                        ),
                        group_id=group_id,
                    )
                )

        # Validate the merged parameter set before writing any submitted group.
        for standard, area_type in (("G", "I"), ("G", "II"), ("Z", "I"), ("Z", "II")):
            selection = SiteSelection(standard=standard, area_type=area_type)
            values = self.parameter_repository.get_parameter_map(selection)
            attribute_name = selection.db_column.lower()
            for row in parsed_rows:
                values[row.name] = getattr(row, attribute_name)
            self.calculator.validate_parameters(selection, values)

        before = self._parameter_snapshot()
        rows_by_group: dict[int, list[ParameterRow]] = {}
        for row in parsed_rows:
            rows_by_group.setdefault(row.group_id, []).append(row)
        for rows in rows_by_group.values():
            self.parameter_repository.save_group_rows(rows)
        after = self._parameter_snapshot()
        changed = self._record_parameter_changes(before, after, "保存参数")
        if not changed:
            self.record_operation(
                level="info",
                action="参数设置",
                message="保存了风险评估参数（没有数值变化）",
                details=f"检查参数数量：{len(parsed_rows)}",
            )
        return self.list_parameters()

    def _parameter_snapshot(self) -> dict[tuple[int, str], ParameterRow]:
        """读取当前参数值，供保存前后做精确差异比较。"""
        return {
            (group_id, row.name): row
            for group_id in PARAMETER_GROUPS
            for row in self.parameter_repository.list_group_rows(group_id)
        }

    def _record_parameter_changes(
        self,
        before: dict[tuple[int, str], ParameterRow],
        after: dict[tuple[int, str], ParameterRow],
        operation: str,
    ) -> int:
        """把参数保存前后的每个数值变化写成一条独立日志。"""
        changed_count = 0
        for key in sorted(set(before) & set(after)):
            old_row = before[key]
            new_row = after[key]
            for column_name, selection_label in PARAMETER_VALUE_COLUMNS:
                old_value = getattr(old_row, column_name)
                new_value = getattr(new_row, column_name)
                if old_value == new_value:
                    continue
                changed_count += 1
                change_details = (
                    f"参数：{new_row.label}（{new_row.name}）；"
                    f"分组：{PARAMETER_GROUPS[new_row.group_id]}；"
                    f"单位：{new_row.unit or '无'}；"
                    f"适用范围：{selection_label}；"
                    f"原值：{old_value}；新值：{new_value}"
                )
                self.record_operation(
                    level="info",
                    action="参数设置",
                    message=f"{operation}：{new_row.label}",
                    details=change_details,
                )
        return changed_count

    def calculate(self, payload: dict[str, object]) -> dict[str, object]:
        selected = self.workspace_repository.list_selected_pollutants()
        if not selected:
            raise ValueError("请先把污染物加入工作区")

        raw_pathways = payload.get("pathways")
        pathway_payload = raw_pathways if isinstance(raw_pathways, dict) else {}
        # 前端约定传入布尔值；不要把字符串 "false" 等非空值误判为 True。
        pathways = {key: pathway_payload.get(key) is True for key in PATHWAY_KEYS}
        if not any(pathways.values()):
            raise ValueError("请至少选择一个暴露途径")

        selection = SiteSelection(
            standard=str(payload.get("standard", "G")),
            area_type=str(payload.get("area_type", "I")),
        )
        self.calculator.validate_selection(selection)
        try:
            results = self.calculator.calculate(selection, selected, pathways)
        except Exception as error:
            self.record_operation(
                level="error",
                action="风险计算",
                message="风险计算失败",
                details=str(error),
            )
            raise
        self.result_repository.replace_results(results)
        self.record_operation(
            level="info",
            action="风险计算",
            message="风险计算完成",
            details=(
                f"标准：{selection.standard}，用地类型：{selection.area_type}，"
                f"暴露途径数量：{sum(pathways.values())}"
            ),
        )
        return {"tables": serialize_results(self.result_repository)}

    def list_results(self) -> dict[str, object]:
        return {"tables": serialize_results(self.result_repository)}

    def export_results(self) -> bytes:
        self.record_operation(
            level="info",
            action="文件导出",
            message="导出了风险评估结果",
        )
        return build_xlsx(build_export_rows(self.result_repository))

    def export_project(self) -> bytes:
        """Export the complete assessment state as a portable project file."""
        return export_project_database()

    def import_project(self, content: bytes) -> dict[str, object]:
        """Validate and open a previously saved project database."""
        replace_runtime_database(content)
        self.record_operation(
            level="info",
            action="项目",
            message="打开了项目文件",
        )
        return self.health()

    def update_project_metadata(self, payload: dict[str, object]) -> dict[str, object]:
        """Save project name and calculation selections beside the assessment data."""
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("项目名称不能为空")
        if len(name) > MAX_TEXT_FIELD_LENGTH:
            raise ValueError(f"项目名称不能超过 {MAX_TEXT_FIELD_LENGTH} 个字符")

        standard = str(payload.get("standard", "G"))
        area_type = str(payload.get("area_type", "I"))
        if standard not in {"G", "Z"}:
            raise ValueError("适用标准参数无效")
        if area_type not in {"I", "II"}:
            raise ValueError("用地类型参数无效")
        raw_pathways = payload.get("pathways")
        if not isinstance(raw_pathways, dict):
            raise ValueError("暴露途径参数必须是对象")

        previous = read_project_metadata()
        project = write_project_metadata(
            name=name,
            standard=standard,
            area_type=area_type,
            pathways={key: raw_pathways.get(key) is True for key in PATHWAY_KEYS},
        )
        changed_fields = [
            field
            for field in ("name", "standard", "area_type", "pathways")
            if previous.get(field) != project.get(field)
        ]
        if changed_fields:
            self.record_operation(
                level="info",
                action="项目设置",
                message="更新了项目名称或评估条件",
                details=f"变更字段：{'、'.join(changed_fields)}",
            )
        return {"project": project}

    def create_project(
        self, payload: dict[str, object] | None = None
    ) -> dict[str, object]:
        """Start a clean assessment without deleting the pollutant library.

        A new project must not inherit mutable assessment state from the previous
        project.  The catalog remains shared, while the workspace, calculated
        results, and temporary parameter edits all return to their defaults.
        """
        # 保持对旧测试/插件中通过 __new__ 创建的精简对象兼容。
        project_lock = getattr(self, "_project_lock", None)
        if project_lock is None:
            project_lock = threading.Lock()
            self._project_lock = project_lock
        with project_lock:
            self.workspace_repository.clear_workspace()
            self.parameter_repository.reset_defaults()
            self.update_project_metadata(payload or {})
            self.operation_log_repository.clear()
            self.record_operation(
                level="info",
                action="项目",
                message="新建了项目",
                details=str(payload.get("name", "")) if payload else "",
            )
            return self.health()

    def login(self, payload: dict[str, object]) -> dict[str, object]:
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not username or not password:
            raise ValueError("用户名和密码不能为空")
        if (
            len(username) > MAX_TEXT_FIELD_LENGTH
            or len(password) > MAX_TEXT_FIELD_LENGTH
        ):
            raise ValueError(f"用户名和密码长度不能超过 {MAX_TEXT_FIELD_LENGTH} 个字符")
        success = self.auth_repository.validate(username, password)
        if not success:
            self.record_operation(
                level="warning",
                action="管理员登录",
                message=f"管理员登录失败：{username}",
            )
            return {"success": False, "username": "", "token": ""}
        token = secrets.token_urlsafe(32)
        with self._session_lock:
            self._remove_expired_sessions()
            self._admin_sessions[token] = (
                username,
                time.monotonic() + ADMIN_SESSION_SECONDS,
            )
        self.record_operation(
            level="info",
            action="管理员登录",
            message=f"管理员登录成功：{username}",
        )
        return {"success": True, "username": username, "token": token}

    def validate_admin_session(self, token: str) -> str | None:
        if not token:
            return None
        with self._session_lock:
            self._remove_expired_sessions()
            session = self._admin_sessions.get(token)
            return session[0] if session else None

    def logout(self, token: str) -> dict[str, object]:
        with self._session_lock:
            self._admin_sessions.pop(token, None)
        self.record_operation(
            level="info",
            action="管理员登录",
            message="管理员退出登录",
        )
        return {"success": True}

    def update_password(
        self,
        payload: dict[str, object],
        username: str,
    ) -> dict[str, object]:
        old_password = str(payload.get("old_password", "")).strip()
        new_password = str(payload.get("new_password", "")).strip()
        if not old_password or not new_password:
            raise ValueError("原密码和新密码不能为空")
        if (
            len(old_password) > MAX_TEXT_FIELD_LENGTH
            or len(new_password) > MAX_TEXT_FIELD_LENGTH
        ):
            raise ValueError(f"密码长度不能超过 {MAX_TEXT_FIELD_LENGTH} 个字符")
        if len(new_password) < 8:
            raise ValueError("新密码至少需要 8 个字符")
        if not self.auth_repository.validate(username, old_password):
            raise ValueError("原密码输入错误")
        success = self.auth_repository.update_password(username, new_password) > 0
        if success:
            with self._session_lock:
                self._admin_sessions.clear()
            self.record_operation(
                level="info",
                action="管理员设置",
                message=f"管理员 {username} 修改了密码",
            )
        return {"success": success}

    def _remove_expired_sessions(self) -> None:
        now = time.monotonic()
        expired = [
            token
            for token, (_username, expires_at) in self._admin_sessions.items()
            if expires_at <= now
        ]
        for token in expired:
            self._admin_sessions.pop(token, None)

    def add_pollutant(self, payload: dict[str, object]) -> dict[str, object]:
        pollutant = self._build_pollutant(payload)
        self.catalog_repository.add_pollutant(pollutant)
        self.record_operation(
            level="info",
            action="污染物库",
            message=f"新增污染物：{pollutant.name}",
        )
        return self.list_catalog(str(payload.get("keyword", "")))

    def update_pollutant(
        self,
        pollutant_id: int,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if self.catalog_repository.get_pollutant(pollutant_id) is None:
            raise ValueError("未找到要更新的污染物")
        if self.catalog_repository.count_workspace_references(pollutant_id):
            raise ValueError("该污染物已在工作区中使用，请先移除工作区记录")
        pollutant = self._build_pollutant(payload, pollutant_id)
        self.catalog_repository.update_pollutant(pollutant)
        self.record_operation(
            level="info",
            action="污染物库",
            message=f"更新污染物：{pollutant.name}",
            details=f"污染物编号：{pollutant.id}",
        )
        return self.list_catalog(str(payload.get("keyword", "")))

    def delete_pollutant(self, pollutant_id: int, keyword: str) -> dict[str, object]:
        if self.catalog_repository.get_pollutant(pollutant_id) is None:
            raise ValueError("未找到要删除的污染物")
        if self.catalog_repository.count_workspace_references(pollutant_id):
            raise ValueError("该污染物已在工作区中使用，请先移除工作区记录")
        self.catalog_repository.delete_pollutant(pollutant_id)
        self.record_operation(
            level="info",
            action="污染物库",
            message=f"删除了污染物编号：{pollutant_id}",
        )
        return self.list_catalog(keyword)

    def _build_pollutant(
        self, payload: dict[str, object], pollutant_id: int = 0
    ) -> Pollutant:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("污染物名称不能为空")
        if len(name) > MAX_TEXT_FIELD_LENGTH:
            raise ValueError(f"污染物名称不能超过 {MAX_TEXT_FIELD_LENGTH} 个字符")
        english_name = str(payload.get("english_name", "")).strip()
        if len(english_name) > MAX_TEXT_FIELD_LENGTH:
            raise ValueError(f"污染物英文名不能超过 {MAX_TEXT_FIELD_LENGTH} 个字符")
        values = {
            field: self._parse_non_negative_decimal(payload.get(field, default), label)
            for field, (label, default) in POLLUTANT_DECIMAL_FIELDS.items()
        }
        return Pollutant(
            id=pollutant_id,
            name=name,
            english_name=english_name,
            **values,
        )

    @staticmethod
    def _parse_finite_decimal(value: object, label: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"{label}不是合法数字：{value}") from None
        if not parsed.is_finite():
            raise ValueError(f"{label}必须是有限数字：{value}")
        return parsed

    @classmethod
    def _parse_non_negative_decimal(cls, value: object, label: str) -> Decimal:
        parsed = cls._parse_finite_decimal(value, label)
        if parsed < 0:
            raise ValueError(f"{label}不能小于 0：{value}")
        return parsed

    @staticmethod
    def _parse_positive_integer(value: object, label: str) -> int:
        if isinstance(value, bool) or value in (None, ""):
            raise ValueError(f"{label}必须是正整数")
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"{label}必须是正整数：{value}") from None
        if (
            not parsed.is_finite()
            or parsed != parsed.to_integral_value()
            or parsed <= 0
        ):
            raise ValueError(f"{label}必须是正整数：{value}")
        return int(parsed)

    @classmethod
    def _parse_parameter_decimal(
        cls,
        value: object,
        label: str,
        column_label: str,
    ) -> Decimal:
        if value in (None, ""):
            raise ValueError(f"参数“{label}”在{column_label}中不能为空")
        return cls._parse_finite_decimal(value, f"参数“{label}”在{column_label}中")
