from __future__ import annotations

from risk_backend.models.entities import (
    Pollutant,
    PollutantConcentration,
    SelectedPollutant,
    to_decimal,
)
from risk_backend.repositories.database import connect

# 这些表都是“与当前工作区强相关”的运行时表。
# 一个污染物被加入工作区后，除了目录临时表和浓度表以外，
# 还需要在多张结果表中预留对应行，后续计算时直接按工作区序号更新即可。
RESULT_TABLES = (
    "db_exposure_ca",
    "db_exposure_nc",
    "db_hq",
    "db_cr",
    "db_pcr",
    "db_phq",
    "db_cv",
)
SQL_LOOKUP_BATCH_SIZE = 500


class WorkspaceRepository:
    """工作区仓储层。

    这一层负责处理“当前评估现场”相关的数据库操作，包括：
    1. 列出当前工作区中的污染物。
    2. 把目录中的污染物插入工作区。
    3. 删除/清空工作区。
    4. 更新工作区中每一条记录的浓度。

    可以把它理解成“工作台数据库适配器”。
    """

    def list_selected_pollutants(self) -> list[SelectedPollutant]:
        """读取当前工作区的完整污染物条目。

        这里一次性把三类信息 join 出来：
        - db_pol_temp: 工作区里选中了哪些污染物
        - db_pol:      污染物基础理化参数
        - db_pol_con:  本次评估填写的浓度

        之所以返回 SelectedPollutant，而不是原始 sqlite Row，
        是为了让上层服务和接口层不用再关心数据库列名细节。
        """
        with connect() as con:
            rows = con.execute(
                """
                select
                    t.number as workspace_number,
                    t.ID as pollutant_id,
                    t.p_name as p_name,
                    t.e_name as e_name,
                    p.Henry, p.Da, p.Dw, p.Koc, p.S, p.SFo, p.IUR, p.RfDo, p.RfC, p.ABSgi, p.ABSd, p.SAF, p.Kp,
                    c.Surface_con, c.Lower_soil_con, c.Groundwater_con, c.Groundwater_pro_con
                from db_pol_temp t
                join db_pol p on p.number = t.ID
                join db_pol_con c on c.number = t.number
                order by t.number
                """
            ).fetchall()

        selected: list[SelectedPollutant] = []
        for row in rows:
            pollutant = Pollutant(
                id=int(row["pollutant_id"]),
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
            concentration = PollutantConcentration(
                workspace_number=int(row["workspace_number"]),
                pollutant_id=int(row["pollutant_id"]),
                name=row["p_name"] or "",
                english_name=row["e_name"] or "",
                surface_concentration=to_decimal(row["Surface_con"]),
                lower_soil_concentration=to_decimal(row["Lower_soil_con"]),
                groundwater_concentration=to_decimal(row["Groundwater_con"]),
                groundwater_protection_concentration=to_decimal(
                    row["Groundwater_pro_con"]
                ),
            )
            selected.append(
                SelectedPollutant(
                    workspace_number=int(row["workspace_number"]),
                    pollutant=pollutant,
                    concentration=concentration,
                )
            )
        return selected

    def count_selected_pollutants(self) -> int:
        """统计当前工作区污染物条目数。"""
        with connect() as con:
            row = con.execute("select count(*) as total from db_pol_temp").fetchone()
        return int(row["total"] if row else 0)

    def _insert_workspace_row(
        self,
        con,
        pollutant: Pollutant,
        *,
        surface_concentration=0.0,
        lower_soil_concentration=0.0,
        groundwater_concentration=0.0,
        groundwater_protection_concentration=0.0,
    ) -> SelectedPollutant:
        """在一个已有连接中插入单条工作区记录。

        这个内部方法同时服务于：
        - 普通单条加入
        - Excel 批量导入

        两者的主要区别只在“浓度值来自哪里”，插入逻辑本身是同一套。
        """
        cursor = con.execute(
            "insert into db_pol_temp (ID, p_name, e_name) values (?, ?, ?)",
            (pollutant.id, pollutant.name, pollutant.english_name),
        )
        workspace_number = int(cursor.lastrowid)
        con.execute(
            """
            insert into db_pol_con (
                number, ID, p_name, e_name, Surface_con, Lower_soil_con, Groundwater_con, Groundwater_pro_con
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_number,
                pollutant.id,
                pollutant.name,
                pollutant.english_name,
                float(surface_concentration),
                float(lower_soil_concentration),
                float(groundwater_concentration),
                float(groundwater_protection_concentration),
            ),
        )
        for table in RESULT_TABLES:
            con.execute(
                f"insert into {table} (number, ID, p_name, e_name) values (?, ?, ?, ?)",
                (
                    workspace_number,
                    pollutant.id,
                    pollutant.name,
                    pollutant.english_name,
                ),
            )
        concentration = PollutantConcentration(
            workspace_number=workspace_number,
            pollutant_id=pollutant.id,
            name=pollutant.name,
            english_name=pollutant.english_name,
            surface_concentration=to_decimal(surface_concentration),
            lower_soil_concentration=to_decimal(lower_soil_concentration),
            groundwater_concentration=to_decimal(groundwater_concentration),
            groundwater_protection_concentration=to_decimal(
                groundwater_protection_concentration
            ),
        )
        return SelectedPollutant(
            workspace_number=workspace_number,
            pollutant=pollutant,
            concentration=concentration,
        )

    def add_pollutant(self, pollutant: Pollutant) -> int:
        """把一个污染物加入工作区，并返回新生成的工作区序号。

        这里有两个教学上很重要的点：
        1. 现在允许“同一个污染物加入多次”，因此不能再按 pollutant.id 去重。
        2. 数据不是只写一张表，而是要同步写入工作区表、浓度表和所有结果表。

        返回的 workspace_number 会被前端用来：
        - 自动选中新加入的那一行
        - 做短暂高亮
        - 自动滚动到新增位置
        """
        with connect() as con:
            item = self._insert_workspace_row(con, pollutant)
        return item.workspace_number

    def import_pollutants(
        self,
        entries: list[dict[str, object]],
    ) -> list[SelectedPollutant]:
        """批量导入工作区污染物及浓度。

        Excel 导入的核心目标是“少开连接、少做往返”。
        因此这里把多条记录放进同一事务里一次性写完。
        """
        with connect() as con:
            imported = [
                self._insert_workspace_row(
                    con,
                    entry["pollutant"],
                    surface_concentration=entry["surface_concentration"],
                    lower_soil_concentration=entry["lower_soil_concentration"],
                    groundwater_concentration=entry["groundwater_concentration"],
                    groundwater_protection_concentration=entry[
                        "groundwater_protection_concentration"
                    ],
                )
                for entry in entries
            ]
        return imported

    def remove_workspace_row(self, workspace_number: int) -> None:
        """删除工作区中的某一行。

        因为项目的结果表是按工作区序号一一对应的，
        所以删除工作区记录时，相关浓度和结果也必须一起删除。
        """
        with connect() as con:
            con.execute("delete from db_pol_temp where number = ?", (workspace_number,))
            con.execute("delete from db_pol_con where number = ?", (workspace_number,))
            for table in RESULT_TABLES:
                con.execute(
                    f"delete from {table} where number = ?", (workspace_number,)
                )

    def clear_workspace(self) -> None:
        """清空整个工作区。"""
        with connect() as con:
            con.execute("delete from db_pol_temp")
            con.execute("delete from db_pol_con")
            for table in RESULT_TABLES:
                con.execute(f"delete from {table}")

    def update_concentrations(self, items: list[PollutantConcentration]) -> None:
        """批量更新工作区浓度。

        前端弹窗保存时会一次性提交所有行，因此这里采用批量循环更新。
        更新依据是 workspace_number，而不是 pollutant_id，
        原因同样是：同一污染物可能在工作区里出现多次。
        """
        if not items:
            return
        workspace_numbers = [item.workspace_number for item in items]
        if len(workspace_numbers) != len(set(workspace_numbers)):
            raise ValueError("工作区浓度数据中存在重复序号")

        with connect() as con:
            existing: dict[int, int] = {}
            for start in range(0, len(workspace_numbers), SQL_LOOKUP_BATCH_SIZE):
                batch = workspace_numbers[start : start + SQL_LOOKUP_BATCH_SIZE]
                placeholders = ", ".join("?" for _item in batch)
                rows = con.execute(
                    f"select number, ID from db_pol_temp where number in ({placeholders})",
                    batch,
                ).fetchall()
                existing.update({int(row["number"]): int(row["ID"]) for row in rows})
            missing = [number for number in workspace_numbers if number not in existing]
            if missing:
                missing_text = "、".join(str(number) for number in missing[:5])
                raise ValueError(f"未找到工作区序号：{missing_text}")
            mismatched = [
                item.workspace_number
                for item in items
                if existing[item.workspace_number] != item.pollutant_id
            ]
            if mismatched:
                numbers = "、".join(str(number) for number in mismatched[:5])
                raise ValueError(f"工作区序号与污染物编号不匹配：{numbers}")
            for item in items:
                con.execute(
                    """
                    update db_pol_con
                    set Surface_con = ?, Lower_soil_con = ?, Groundwater_con = ?, Groundwater_pro_con = ?
                    where number = ?
                    """,
                    (
                        float(item.surface_concentration),
                        float(item.lower_soil_concentration),
                        float(item.groundwater_concentration),
                        float(item.groundwater_protection_concentration),
                        item.workspace_number,
                    ),
                )
