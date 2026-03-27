from __future__ import annotations

from risk_backend.models.entities import ParameterRow, SiteSelection, to_decimal
from risk_backend.repositories.database import connect


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


class ParameterRepository:
    def list_group_rows(self, group_id: int) -> list[ParameterRow]:
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
                data_gi=to_decimal(row["data_GI"]),
                data_gii=to_decimal(row["data_GII"]),
                data_zi=to_decimal(row["data_ZI"]),
                data_zii=to_decimal(row["data_ZII"]),
                group_id=row["groupid"],
            )
            for row in rows
        ]

    def reset_defaults(self) -> None:
        with connect() as con:
            con.execute("delete from db_pol_area_par_temp")
            con.execute("insert into db_pol_area_par_temp select * from db_pol_area_par")

    def save_group_rows(self, rows: list[ParameterRow]) -> None:
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
        rows: dict[str, object] = {}
        with connect() as con:
            for name in PARAMETER_NAMES:
                row = con.execute(
                    f"select {selection.db_column} as value from db_pol_area_par_temp where name = ?",
                    (name,),
                ).fetchone()
                rows[name] = to_decimal(row["value"] if row else None)
        return rows

