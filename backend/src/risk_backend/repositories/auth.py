from __future__ import annotations

from risk_backend.repositories.database import connect
from risk_backend.security import hash_password, is_password_hash, verify_password


class AuthRepository:
    """管理员账号仓储层。"""

    def validate(self, username: str, password: str) -> bool:
        """校验用户名和密码是否匹配。"""
        with connect() as con:
            row = con.execute(
                "select password from db_users where userName = ?",
                (username,),
            ).fetchone()
            if row is None or not verify_password(password, str(row["password"] or "")):
                return False

            # 旧运行库若跳过迁移，第一次成功登录时仍会自动升级明文密码。
            if not is_password_hash(str(row["password"] or "")):
                con.execute(
                    "update db_users set password = ? where userName = ?",
                    (hash_password(password), username),
                )
        return True

    def update_password(self, username: str, new_password: str) -> int:
        """更新管理员密码。"""
        with connect() as con:
            cursor = con.execute(
                "update db_users set password = ? where userName = ?",
                (hash_password(new_password), username),
            )
            return cursor.rowcount
