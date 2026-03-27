from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


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
    connection = sqlite3.connect(database_path)
    try:
        for table in WORKSPACE_TABLES:
            connection.execute(f"delete from {table}")
        connection.commit()
    finally:
        connection.close()


def ensure_database() -> Path:
    if not RUNTIME_DB.exists():
        shutil.copy2(TEMPLATE_DB, RUNTIME_DB)
        _clear_workspace_tables(RUNTIME_DB)
    return RUNTIME_DB


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
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
    if RUNTIME_DB.exists():
        RUNTIME_DB.unlink()
    return ensure_database()
