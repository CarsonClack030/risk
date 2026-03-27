from __future__ import annotations

from collections import defaultdict

from risk_backend.models.entities import Pollutant, PollutantConcentration, SelectedPollutant, to_decimal
from risk_backend.repositories.database import connect


RESULT_TABLES = (
    "db_exposure_ca",
    "db_exposure_nc",
    "db_hq",
    "db_cr",
    "db_pcr",
    "db_phq",
    "db_cv",
)


class WorkspaceRepository:
    def list_selected_pollutants(self) -> list[SelectedPollutant]:
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
                groundwater_protection_concentration=to_decimal(row["Groundwater_pro_con"]),
            )
            selected.append(
                SelectedPollutant(
                    workspace_number=int(row["workspace_number"]),
                    pollutant=pollutant,
                    concentration=concentration,
                )
            )
        return selected

    def add_pollutant(self, pollutant: Pollutant) -> int:
        with connect() as con:
            cursor = con.execute(
                "insert into db_pol_temp (ID, p_name, e_name) values (?, ?, ?)",
                (pollutant.id, pollutant.name, pollutant.english_name),
            )
            workspace_number = cursor.lastrowid
            con.execute(
                """
                insert into db_pol_con (
                    number, ID, p_name, e_name, Surface_con, Lower_soil_con, Groundwater_con, Groundwater_pro_con
                ) values (?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0)
                """,
                (workspace_number, pollutant.id, pollutant.name, pollutant.english_name),
            )
            for table in RESULT_TABLES:
                con.execute(
                    f"insert into {table} (number, ID, p_name, e_name) values (?, ?, ?, ?)",
                    (workspace_number, pollutant.id, pollutant.name, pollutant.english_name),
                )
        return int(workspace_number)

    def remove_workspace_row(self, workspace_number: int) -> None:
        with connect() as con:
            con.execute("delete from db_pol_temp where number = ?", (workspace_number,))
            con.execute("delete from db_pol_con where number = ?", (workspace_number,))
            for table in RESULT_TABLES:
                con.execute(f"delete from {table} where number = ?", (workspace_number,))

    def clear_workspace(self) -> None:
        with connect() as con:
            con.execute("delete from db_pol_temp")
            con.execute("delete from db_pol_con")
            for table in RESULT_TABLES:
                con.execute(f"delete from {table}")

    def update_concentrations(self, items: list[PollutantConcentration]) -> None:
        with connect() as con:
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
