from __future__ import annotations

from typing import Iterable

from risk_backend.models.entities import Pollutant, to_decimal
from risk_backend.repositories.database import connect


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
    def list_pollutants(self, keyword: str = "") -> list[Pollutant]:
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
        with connect() as con:
            row = con.execute(
                f"select {', '.join(POLLUTANT_COLUMNS)} from db_pol where number = ?",
                (pollutant_id,),
            ).fetchone()
        return _row_to_pollutant(row) if row else None

    def add_pollutant(self, pollutant: Pollutant) -> int:
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
        with connect() as con:
            cursor = con.execute("delete from db_pol where number = ?", (pollutant_id,))
            return cursor.rowcount

