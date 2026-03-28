from __future__ import annotations

from typing import Iterable

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


class CatalogRepository:
    """污染物目录仓储层。"""

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
