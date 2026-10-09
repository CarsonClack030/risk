from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from risk_backend.repositories.database import OPERATION_LOG_TABLE, connect

MAX_LOG_TEXT_LENGTH = 2_000
MAX_LOG_LIMIT = 5_000


class OperationLogRepository:
    """读写项目内的操作日志。

    日志和工作区、参数、结果一样写入当前 SQLite 文件，因此导出 `.riskproj`
    时会自然地一起保存。这里只保存业务操作和错误摘要，不保存密码或完整请求体。
    参数修改的原值、新值、单位和适用范围统一写入 details，避免日志界面
    出现两个含义重叠的详情列。数据库中的旧 change_details 字段暂时保留，
    用于兼容已经保存的旧项目文件。
    """

    def append(
        self,
        *,
        level: str,
        action: str,
        message: str,
        details: str = "",
        change_details: str = "",
    ) -> None:
        normalized_level = str(level).strip().lower() or "info"
        if normalized_level not in {"info", "warning", "error"}:
            normalized_level = "info"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        merged_details = self._merge_details(details, change_details)
        values = (
            timestamp,
            normalized_level,
            self._limit(action),
            self._limit(message),
            self._limit(merged_details),
            "",
        )
        with connect() as connection:
            connection.execute(
                f"""
                insert into {OPERATION_LOG_TABLE}
                    (timestamp, level, action, message, details, change_details)
                values (?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def clear(self) -> None:
        """Remove logs before a new project starts its own log history."""
        with connect() as connection:
            connection.execute(f"delete from {OPERATION_LOG_TABLE}")

    def list_recent(self, limit: int | None = None) -> list[dict[str, object]]:
        with connect() as connection:
            query = f"""
                select
                    id,
                    timestamp,
                    level,
                    action,
                    message,
                    case
                        when details <> '' and change_details <> ''
                            then details || '；' || change_details
                        when details <> '' then details
                        else change_details
                    end as details
                from {OPERATION_LOG_TABLE}
                order by id desc
            """
            if limit is None:
                rows = connection.execute(query).fetchall()
            else:
                safe_limit = max(1, min(int(limit), MAX_LOG_LIMIT))
                rows = connection.execute(f"{query} limit ?", (safe_limit,)).fetchall()
        return [dict(row) for row in rows]

    def export_csv(self) -> bytes:
        rows = self.list_recent()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["编号", "时间戳", "级别", "操作", "消息", "详细信息"])
        for row in reversed(rows):
            writer.writerow(
                [
                    row["id"],
                    row["timestamp"],
                    row["level"],
                    row["action"],
                    row["message"],
                    row["details"],
                ]
            )
        # UTF-8 BOM 让 Excel 在 Windows 下自动识别中文，而不会出现乱码。
        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def _limit(value: object) -> str:
        return str(value or "")[:MAX_LOG_TEXT_LENGTH]

    @classmethod
    def _merge_details(cls, details: object, change_details: object) -> str:
        """Keep legacy callers working while storing one visible detail value."""
        primary = str(details or "").strip()
        legacy = str(change_details or "").strip()
        if primary and legacy:
            return f"{primary}；{legacy}"
        return primary or legacy
