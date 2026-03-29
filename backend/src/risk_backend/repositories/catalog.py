from __future__ import annotations

import re

from risk_backend.models.entities import Pollutant, to_decimal
from risk_backend.repositories.database import connect


# db_pol 表的列顺序定义。
# 这里集中管理后，查询目录和读取单个污染物都可以复用同一份字段列表。
POLLUTANT_COLUMNS = (
    "number",
    "p_name",
    "e_name",
    "Henry",
    "Da",
    "Dw",
    "Koc",
    "S",
    "SFo",
    "IUR",
    "RfDo",
    "RfC",
    "ABSgi",
    "ABSd",
    "SAF",
    "Kp",
)
QUALIFIER_PATTERNS = (
    r"（[^）]*）",
    r"\([^)]*\)",
    r"【[^】]*】",
    r"\[[^\]]*\]",
)


def _row_to_pollutant(row) -> Pollutant:
    """把数据库行转换成污染物实体对象。"""
    return Pollutant(
        id=int(row["number"]),
        name=row["p_name"] or "",
        english_name=row["e_name"] or "",
        henry=to_decimal(row["Henry"]),
        da=to_decimal(row["Da"]),
        dw=to_decimal(row["Dw"]),
        koc=to_decimal(row["Koc"]),
        solubility=to_decimal(row["S"]),
        sfo=to_decimal(row["SFo"]),
        iur=to_decimal(row["IUR"]),
        rfdo=to_decimal(row["RfDo"]),
        rfc=to_decimal(row["RfC"]),
        absgi=to_decimal(row["ABSgi"]),
        absd=to_decimal(row["ABSd"]),
        saf=to_decimal(row["SAF"], to_decimal(1)),
        kp=to_decimal(row["Kp"]),
    )


def _normalize_pollutant_name(value: str) -> str:
    """把污染物名称归一化，方便做模糊匹配。

    Excel 导入时，用户经常会写一个“更短的通俗叫法”，例如：
    - 砷
    - 六六六
    - 苯并[a]芘

    而数据库里可能保存的是：
    - 砷（无机）
    - 六六六（总量）

    这里会移除常见括号补充说明，并去掉空白，
    让“主名称”更容易对齐。
    """
    normalized = str(value or "").strip()
    for pattern in QUALIFIER_PATTERNS:
        normalized = re.sub(pattern, "", normalized)
    return "".join(normalized.split()).lower()


def _choose_single_match(matches: list[Pollutant], query: str) -> Pollutant | None:
    """从候选项里选出唯一匹配。

    如果只有一条就直接返回；
    如果有多条并列最优，就明确报错，避免把错误污染物静默导入工作区。
    """
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    names = "、".join(item.name for item in matches[:3])
    more = " 等" if len(matches) > 3 else ""
    raise ValueError(f"污染物名称“{query}”匹配到多条记录：{names}{more}，请补全名称或直接填写编号")


class CatalogRepository:
    """污染物目录仓储层。"""

    def count_pollutants(self) -> int:
        """统计污染物目录总数。

        这比先读取整张目录再 `len(...)` 更适合健康检查或首页指标卡场景。
        """
        with connect() as con:
            row = con.execute("select count(*) as total from db_pol").fetchone()
        return int(row["total"] if row else 0)

    def list_pollutants(self, keyword: str = "") -> list[Pollutant]:
        """按关键词查询污染物目录。

        关键词同时匹配中文名和英文名。
        当前项目故意不在前端默认加载全量目录，
        因此这个方法会非常频繁地被调用。
        """
        sql = f"select {', '.join(POLLUTANT_COLUMNS)} from db_pol where 1=1"
        params: list[object] = []
        if keyword.strip():
            sql += " and (p_name like ? or e_name like ?)"
            like = f"%{keyword.strip()}%"
            params.extend([like, like])
        sql += " order by number"
        with connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [_row_to_pollutant(row) for row in rows]

    def get_pollutant(self, pollutant_id: int) -> Pollutant | None:
        """按编号读取单个污染物。"""
        with connect() as con:
            row = con.execute(
                f"select {', '.join(POLLUTANT_COLUMNS)} from db_pol where number = ?",
                (pollutant_id,),
            ).fetchone()
        return _row_to_pollutant(row) if row else None

    def find_by_name(self, name: str) -> Pollutant | None:
        """按中文名查找污染物，优先精确匹配，再尝试模糊匹配。

        当前导入场景里最常见的需求是：
        Excel 中写“砷”，数据库中保存为“砷（无机）”。

        因此这里的匹配顺序是：
        1. 原始名称精确匹配
        2. 去掉括号补充说明后的“主名称”匹配
        3. 主名称的前缀 / 包含匹配
        """
        query = name.strip()
        if not query:
            return None
        with connect() as con:
            exact_rows = con.execute(
                f"select {', '.join(POLLUTANT_COLUMNS)} from db_pol where p_name = ? order by number",
                (query,),
            ).fetchall()
            if exact_rows:
                return _choose_single_match([_row_to_pollutant(row) for row in exact_rows], query)

            candidate_rows = con.execute(
                f"""
                select {', '.join(POLLUTANT_COLUMNS)}
                from db_pol
                where p_name like ? or p_name like ?
                order by number
                """,
                (f"%{query}%", f"{query}%"),
            ).fetchall()

        normalized_query = _normalize_pollutant_name(query)
        if not normalized_query:
            return None

        scored: list[tuple[int, Pollutant]] = []
        seen_ids: set[int] = set()
        for row in candidate_rows:
            pollutant = _row_to_pollutant(row)
            if pollutant.id in seen_ids:
                continue
            seen_ids.add(pollutant.id)
            normalized_name = _normalize_pollutant_name(pollutant.name)
            score = 0
            if normalized_name == normalized_query:
                score = 100
            elif pollutant.name.startswith(query) or query.startswith(pollutant.name):
                score = 90
            elif normalized_name.startswith(normalized_query) or normalized_query.startswith(normalized_name):
                score = 80
            elif query in pollutant.name or pollutant.name in query:
                score = 70
            elif normalized_query in normalized_name or normalized_name in normalized_query:
                score = 60
            if score > 0:
                scored.append((score, pollutant))

        if not scored:
            return None

        scored.sort(key=lambda item: (-item[0], item[1].id))
        top_score = scored[0][0]
        top_matches = [pollutant for score, pollutant in scored if score == top_score]
        return _choose_single_match(top_matches, query)

    def find_by_english_name(self, english_name: str) -> Pollutant | None:
        """按英文名精确查找污染物，大小写不敏感。"""
        with connect() as con:
            row = con.execute(
                f"select {', '.join(POLLUTANT_COLUMNS)} from db_pol where lower(e_name) = lower(?) order by number limit 1",
                (english_name.strip(),),
            ).fetchone()
        return _row_to_pollutant(row) if row else None

    def add_pollutant(self, pollutant: Pollutant) -> int:
        """新增污染物目录条目。"""
        with connect() as con:
            cursor = con.execute(
                """
                insert into db_pol(
                    p_name, e_name, Henry, Da, Dw, Koc, S, SFo, IUR, RfDo, RfC, ABSgi, ABSd, SAF, Kp
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pollutant.name,
                    pollutant.english_name,
                    float(pollutant.henry),
                    float(pollutant.da),
                    float(pollutant.dw),
                    float(pollutant.koc),
                    float(pollutant.solubility),
                    float(pollutant.sfo),
                    float(pollutant.iur),
                    float(pollutant.rfdo),
                    float(pollutant.rfc),
                    float(pollutant.absgi),
                    float(pollutant.absd),
                    float(pollutant.saf),
                    float(pollutant.kp),
                ),
            )
            return cursor.rowcount

    def update_pollutant(self, pollutant: Pollutant) -> int:
        """更新污染物目录条目。"""
        with connect() as con:
            cursor = con.execute(
                """
                update db_pol
                set p_name = ?, e_name = ?, Henry = ?, Da = ?, Dw = ?, Koc = ?, S = ?, SFo = ?,
                    IUR = ?, RfDo = ?, RfC = ?, ABSgi = ?, ABSd = ?, SAF = ?, Kp = ?
                where number = ?
                """,
                (
                    pollutant.name,
                    pollutant.english_name,
                    float(pollutant.henry),
                    float(pollutant.da),
                    float(pollutant.dw),
                    float(pollutant.koc),
                    float(pollutant.solubility),
                    float(pollutant.sfo),
                    float(pollutant.iur),
                    float(pollutant.rfdo),
                    float(pollutant.rfc),
                    float(pollutant.absgi),
                    float(pollutant.absd),
                    float(pollutant.saf),
                    float(pollutant.kp),
                    pollutant.id,
                ),
            )
            return cursor.rowcount

    def delete_pollutant(self, pollutant_id: int) -> int:
        """删除污染物目录条目。"""
        with connect() as con:
            cursor = con.execute("delete from db_pol where number = ?", (pollutant_id,))
            return cursor.rowcount
