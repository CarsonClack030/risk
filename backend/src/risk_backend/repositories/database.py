from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# 这个文件负责“运行数据库”的生命周期管理。
# 模板数据库是只读资源，真正运行时会复制到用户目录下，
# 这样桌面应用才能在本地持续读写，而不会污染打包内置资源。

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DB = PACKAGE_ROOT / "resources" / "template.db"
APP_NAME = "Risk Studio"
PROJECT_ROOT = PACKAGE_ROOT.parents[2]
WORKSPACE_TABLES = (
    "db_pol_temp",
    "db_pol_con",
    "db_exposure_ca",
    "db_exposure_nc",
    "db_hq",
    "db_cr",
    "db_pcr",
    "db_phq",
    "db_cv",
)


def application_data_dir() -> Path:
    """按平台规则决定应用数据目录。

    优先级：
    1. 如果显式设置了 RISK_APP_DATA_DIR，就使用它。
       这对测试特别有用，因为可以把数据库重定向到临时目录。
    2. 否则按 macOS / Windows / Linux 各自习惯选择默认目录。
    """
    override = os.environ.get("RISK_APP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / APP_NAME
    xdg = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return xdg / APP_NAME


def runtime_app_dir() -> Path:
    """找到一个可写的运行目录。

    第一选择是正式的应用数据目录；
    如果因为权限等原因不可写，就回退到项目根目录下的 .runtime_data。
    """
    candidates = [
        application_data_dir(),
        PROJECT_ROOT / ".runtime_data",
    ]
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    raise OSError("无法创建运行数据库目录")


APP_DIR = runtime_app_dir()
RUNTIME_DB = APP_DIR / "risk_app.db"


def _clear_workspace_tables(database_path: Path) -> None:
    """清空模板数据库里与“当前会话”有关的表。

    模板库可能保留结构和基础字典表，但工作区、结果表不应该带入历史数据，
    所以首次复制到运行库后会主动清一次。
    """
    connection = sqlite3.connect(database_path)
    try:
        for table in WORKSPACE_TABLES:
            connection.execute(f"delete from {table}")
        connection.commit()
    finally:
        connection.close()


def ensure_database() -> Path:
    """确保运行数据库存在。

    首次运行时：
    - 复制 template.db
    - 清空工作区相关表
    后续运行时：
    - 直接复用已存在的 risk_app.db
    """
    if not RUNTIME_DB.exists():
        shutil.copy2(TEMPLATE_DB, RUNTIME_DB)
        _clear_workspace_tables(RUNTIME_DB)
    return RUNTIME_DB


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """统一的数据库连接上下文。

    这个封装替代了手写 try/commit/rollback/close：
    - 正常结束自动提交
    - 发生异常自动回滚
    - 最后总会关闭连接
    """
    database_path = ensure_database()
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def reset_runtime_database() -> Path:
    """删除运行库并重新从模板复制。

    这个函数更适合测试、调试或“恢复出厂状态”的场景。
    """
    if RUNTIME_DB.exists():
        RUNTIME_DB.unlink()
    return ensure_database()
