from __future__ import annotations

from risk_backend.models.entities import ParameterRow, SiteSelection, to_decimal
from risk_backend.repositories.database import connect


# 参数被分成 4 个逻辑分组，对应前端参数弹窗的 4 个标签页。
PARAMETER_GROUPS = {
    1: "污染区参数",
    2: "土壤参数",
    3: "建筑物参数",
    4: "暴露参数",
}


PARAMETER_NAMES = [
    "A", "Ab", "ABSo", "ACR", "AHQ", "ATca", "ATnc", "BWa", "BWc", "d", "DAIRa", "DAIRc",
    "Delta_air", "Delta_gw", "dP", "dsub", "EDa", "EDc", "EFa", "EFc", "EFIa", "EFIc",
    "EFOa", "EFOc", "Eit", "ER", "Ev", "fom", "fspi", "fspo", "GWCRa", "GWCRc", "Ha", "Hc",
    "hcap", "hv", "I", "K_v", "LB", "Lcrack", "Lgw", "LS", "OSIRa", "OSIRc", "PIAF", "PM10",
    "Pws", "Rho_b", "Rho_s", "SAEa", "SAEc", "SERa", "SERc", "SSARa", "SSARc", "Tau",
    "Theta_acap", "Theta_acrack", "Theta_wcap", "Theta_wcrack", "Uair", "Ugw", "W", "WAF",
    "X_crack", "Z_crack", "tc", "ta",
]


# 参数单位属于模型定义，不属于用户可以修改的场地参数，因此不写入数据库。
# 这份映射主要依据 HJ 25.3—2019 附录 G 的参数表；项目额外保留的
# SAEa / SAEc 和 tc / ta 分别使用皮肤面积（cm²）和单次接触时间（h）。
# 使用参数符号作为 key，可以让国家标准、浙江标准四组数值共享同一单位。
PARAMETER_UNITS = {
    # 污染区参数
    "A": "cm²",
    "d": "cm",
    "dsub": "cm",
    "Lgw": "cm",
    "LS": "cm",
    # 土壤参数
    "Delta_air": "cm",
    "Delta_gw": "cm",
    "fom": "g·kg⁻¹",
    "hcap": "cm",
    "hv": "cm",
    "I": "cm·a⁻¹",
    "PM10": "mg·m⁻³",
    "Pws": "kg·kg⁻¹",
    "Rho_b": "kg·dm⁻³",
    "Rho_s": "kg·dm⁻³",
    "Theta_acap": "无量纲",
    "Theta_wcap": "无量纲",
    "Uair": "cm·s⁻¹",
    "Ugw": "cm·a⁻¹",
    "W": "cm",
    # 建筑物参数
    "Ab": "cm²",
    "dP": "g·cm⁻¹·s⁻²",
    "Eit": "无量纲",
    "ER": "次·d⁻¹",
    "K_v": "cm²",
    "LB": "cm",
    "Lcrack": "cm",
    "Tau": "a",
    "Theta_acrack": "无量纲",
    "Theta_wcrack": "无量纲",
    "X_crack": "cm",
    "Z_crack": "cm",
    # 暴露参数
    "ABSo": "无量纲",
    "ACR": "无量纲",
    "AHQ": "无量纲",
    "ATca": "d",
    "ATnc": "d",
    "BWa": "kg",
    "BWc": "kg",
    "DAIRa": "m³·d⁻¹",
    "DAIRc": "m³·d⁻¹",
    "EDa": "a",
    "EDc": "a",
    "EFa": "d·a⁻¹",
    "EFc": "d·a⁻¹",
    "EFIa": "d·a⁻¹",
    "EFIc": "d·a⁻¹",
    "EFOa": "d·a⁻¹",
    "EFOc": "d·a⁻¹",
    "Ev": "次·d⁻¹",
    "fspi": "无量纲",
    "fspo": "无量纲",
    "GWCRa": "L·d⁻¹",
    "GWCRc": "L·d⁻¹",
    "Ha": "cm",
    "Hc": "cm",
    "OSIRa": "mg·d⁻¹",
    "OSIRc": "mg·d⁻¹",
    "PIAF": "无量纲",
    "SAEa": "cm²",
    "SAEc": "cm²",
    "SERa": "无量纲",
    "SERc": "无量纲",
    "SSARa": "mg·cm⁻²",
    "SSARc": "mg·cm⁻²",
    "WAF": "无量纲",
    "tc": "h",
    "ta": "h",
}


class ParameterRepository:
    """参数仓储层。"""

    def list_group_rows(self, group_id: int) -> list[ParameterRow]:
        """读取某一组参数，供前端参数弹窗展示。"""
        with connect() as con:
            rows = con.execute(
                """
                select name, name_ch, data_GI, data_GII, data_ZI, data_ZII, groupid
                from db_pol_area_par_temp
                where groupid = ?
                order by rowid
                """,
                (group_id,),
            ).fetchall()
        return [
            ParameterRow(
                name=row["name"],
                label=row["name_ch"] or row["name"],
                unit=PARAMETER_UNITS[row["name"]],
                data_gi=to_decimal(row["data_GI"]),
                data_gii=to_decimal(row["data_GII"]),
                data_zi=to_decimal(row["data_ZI"]),
                data_zii=to_decimal(row["data_ZII"]),
                group_id=row["groupid"],
            )
            for row in rows
        ]

    def reset_defaults(self) -> None:
        """把临时参数表恢复为系统默认参数。"""
        with connect() as con:
            con.execute("delete from db_pol_area_par_temp")
            con.execute("insert into db_pol_area_par_temp select * from db_pol_area_par")

    def save_group_rows(self, rows: list[ParameterRow]) -> None:
        """保存参数弹窗中的某一组草稿。"""
        with connect() as con:
            for row in rows:
                con.execute(
                    """
                    update db_pol_area_par_temp
                    set data_GI = ?, data_GII = ?, data_ZI = ?, data_ZII = ?
                    where name = ?
                    """,
                    (
                        float(row.data_gi),
                        float(row.data_gii),
                        float(row.data_zi),
                        float(row.data_zii),
                        row.name,
                    ),
                )

    def get_parameter_map(self, selection: SiteSelection) -> dict[str, object]:
        """根据当前标准和用地类型，抽出一整套参数字典。

        这里返回的是扁平字典，例如：
        - A
        - BWa
        - PM10

        后续会在 calculator.py 中被包装成 AttributeMap，
        方便以 `par.BWa` 的方式读取。
        """
        placeholders = ", ".join("?" for _name in PARAMETER_NAMES)
        with connect() as con:
            database_rows = con.execute(
                f"""
                select name, {selection.db_column} as value
                from db_pol_area_par_temp
                where name in ({placeholders})
                """,
                PARAMETER_NAMES,
            ).fetchall()
        values = {row["name"]: to_decimal(row["value"]) for row in database_rows}
        return {name: values.get(name, to_decimal(None)) for name in PARAMETER_NAMES}
