from __future__ import annotations

from risk_backend.models.entities import User
from risk_backend.repositories.database import connect


class AuthRepository:
    def validate(self, username: str, password: str) -> bool:
        with connect() as con:
            row = con.execute(
                "select 1 from db_users where userName = ? and password = ?",
                (username, password),
            ).fetchone()
        return row is not None

    def update_password(self, username: str, new_password: str) -> int:
        with connect() as con:
            cursor = con.execute(
                "update db_users set password = ? where userName = ?",
                (new_password, username),
            )
            return cursor.rowcount

