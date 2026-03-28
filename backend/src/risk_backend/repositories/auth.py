from __future__ import annotations

from risk_backend.models.entities import User
from risk_backend.repositories.database import connect


class AuthRepository:
    """管理员账号仓储层。"""

    def validate(self, username: str, password: str) -> bool:
        """校验用户名和密码是否匹配。"""
        with connect() as con:
            row = con.execute(
                "select 1 from db_users where userName = ? and password = ?",
                (username, password),
            ).fetchone()
        return row is not None

    def update_password(self, username: str, new_password: str) -> int:
        """更新管理员密码。"""
        with connect() as con:
            cursor = con.execute(
                "update db_users set password = ? where userName = ?",
                (new_password, username),
            )
            return cursor.rowcount
