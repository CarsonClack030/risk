from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

from risk_backend.security import hash_password, is_password_hash

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
PROJECT_TABLES = frozenset(
    {
        "db_users",
        "db_pol",
        "db_pol_area_par",
        "db_pol_area_par_temp",
        "db_pol_temp",
        "db_pol_con",
        *WORKSPACE_TABLES,
    }
)
PROJECT_METADATA_TABLE = "risk_project_meta"
OPERATION_LOG_TABLE = "risk_operation_logs"
PROJECT_PATHWAY_KEYS = (
    "ois",
    "dcs",
    "pis",
    "dgw",
    "cgw",
    "iov3",
    "iiv2",
    "iov1",
    "iov2",
    "iiv1",
)
DATABASE_SCHEMA_VERSION = 4
MAX_DATABASE_BACKUPS = 3
MAX_PROJECT_BYTES = 64 * 1024 * 1024
_DATABASE_LOCK = threading.Lock()
KNOWN_UNUSED_PAGE_WARNING = re.compile(
    r"^\*\*\* in database main \*\*\*\n(?:Page \d+: never used\n?)+$"
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


def _backup_database(database_path: Path) -> Path:
    """Create a timestamped copy before changing an existing user database."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = database_path.with_name(f"{database_path.stem}.backup-{timestamp}.db")
    shutil.copy2(database_path, backup_path)
    with suppress(OSError):
        backup_path.chmod(0o600)

    backups = sorted(
        database_path.parent.glob(f"{database_path.stem}.backup-*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale_backup in backups[MAX_DATABASE_BACKUPS:]:
        with suppress(OSError):
            stale_backup.unlink()
    return backup_path


def _checkpoint_database(database_path: Path) -> None:
    """Flush SQLite WAL pages before copying or replacing a database file."""
    connection = sqlite3.connect(database_path, timeout=5)
    try:
        connection.execute("pragma wal_checkpoint(truncate)")
    finally:
        connection.close()


def _prepare_imported_database(database_path: Path) -> Path:
    """Copy an imported database into a sidecar-free SQLite file.

    SQLite's backup API reads a consistent snapshot even when the source uses
    WAL mode.  The destination starts with SQLite's default DELETE journal
    mode, so an atomic file swap never inherits a source ``-wal`` or ``-shm``
    file.
    """
    normalized_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="risk-project-normalized-",
            suffix=".db",
            dir=APP_DIR,
            delete=False,
        ) as normalized:
            normalized_path = Path(normalized.name)
        source = sqlite3.connect(database_path, timeout=5)
        target = sqlite3.connect(normalized_path, timeout=5)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        # 不要把规范化文件再覆盖回 database_path。Windows 可能仍会短暂
        # 锁定刚刚关闭的导入文件，导致 os.replace 报 WinError 5。让调用方
        # 直接使用这个已经关闭连接的规范化文件，可以避开一次不必要的替换。
        _remove_database_sidecars(database_path)
        result = normalized_path
        normalized_path = None
        return result
    finally:
        if normalized_path is not None:
            _remove_database_sidecars(normalized_path)
            with suppress(OSError):
                normalized_path.unlink()


def _remove_database_sidecars(database_path: Path) -> None:
    """Remove WAL sidecars that belong to a database being replaced."""
    for suffix in ("-wal", "-shm"):
        with suppress(OSError):
            database_path.with_name(database_path.name + suffix).unlink()


def _migrate_database(database_path: Path, *, existing_database: bool) -> None:
    """Upgrade an old runtime database without discarding user data."""
    with sqlite3.connect(database_path) as connection:
        current_version = int(connection.execute("pragma user_version").fetchone()[0])

    if current_version > DATABASE_SCHEMA_VERSION:
        raise RuntimeError(
            f"运行数据库版本 {current_version} 高于软件支持的版本 "
            f"{DATABASE_SCHEMA_VERSION}，请升级软件后再试"
        )
    # 旧版已经写入当前版本号但缺少附加表时，直接补表即可；
    # 只有真正发生版本迁移时才创建一次用户数据库备份，避免每次启动都产生备份文件。
    if existing_database and current_version < DATABASE_SCHEMA_VERSION:
        _backup_database(database_path)

    with sqlite3.connect(database_path) as connection:
        if current_version < 1:
            users = connection.execute("select id, password from db_users").fetchall()
            for user_id, stored_password in users:
                password = str(stored_password or "")
                if not is_password_hash(password):
                    connection.execute(
                        "update db_users set password = ? where id = ?",
                        (hash_password(password), user_id),
                    )
        # 不只依赖 user_version。部分旧版数据库曾经把版本号写完，
        # 但在创建表前被中断，导致“版本号正确、表却不存在”。
        # 每次启动都用 IF NOT EXISTS 做一次轻量结构自检，避免新建项目时才暴露问题。
        connection.execute(
            f"""
            create table if not exists {PROJECT_METADATA_TABLE} (
                key text primary key,
                value text not null
            )
            """
        )
        connection.execute(
            f"""
            create table if not exists {OPERATION_LOG_TABLE} (
                id integer primary key autoincrement,
                timestamp text not null,
                level text not null,
                action text not null,
                message text not null,
                details text not null default '',
                change_details text not null default ''
            )
            """
        )
        columns = {
            row[1]
            for row in connection.execute(
                f"pragma table_info({OPERATION_LOG_TABLE})"
            ).fetchall()
        }
        if "change_details" not in columns:
            connection.execute(
                f"""
                alter table {OPERATION_LOG_TABLE}
                add column change_details text not null default ''
                """
            )
        connection.execute(
            f"""
            create index if not exists idx_{OPERATION_LOG_TABLE}_timestamp
            on {OPERATION_LOG_TABLE} (timestamp desc, id desc)
            """
        )
        connection.execute(f"pragma user_version = {DATABASE_SCHEMA_VERSION}")


def ensure_database() -> Path:
    """确保运行数据库存在。

    首次运行时：
    - 复制 template.db
    - 清空工作区相关表
    后续运行时：
    - 直接复用已存在的 risk_app.db
    """
    with _DATABASE_LOCK:
        existed = RUNTIME_DB.exists()
        if not existed:
            shutil.copy2(TEMPLATE_DB, RUNTIME_DB)
            _clear_workspace_tables(RUNTIME_DB)
        _migrate_database(RUNTIME_DB, existing_database=existed)
        with suppress(OSError):
            RUNTIME_DB.chmod(0o600)
    return RUNTIME_DB


def export_project_database() -> bytes:
    """Export a consistent SQLite snapshot for a `.riskproj` file."""
    ensure_database()
    snapshot_path: Path | None = None
    try:
        # NamedTemporaryFile keeps the file handle open while the context is
        # active. Windows then refuses to let SQLite open the same path again.
        # mkstemp gives us a unique path; close its descriptor before SQLite
        # opens the destination database.
        file_descriptor, file_name = tempfile.mkstemp(
            prefix="risk-project-", suffix=".db", dir=APP_DIR
        )
        os.close(file_descriptor)
        snapshot_path = Path(file_name)
        with _DATABASE_LOCK:
            with (
                sqlite3.connect(RUNTIME_DB) as source,
                sqlite3.connect(snapshot_path) as target,
            ):
                source.backup(target)
            return snapshot_path.read_bytes()
    finally:
        if snapshot_path is not None:
            _remove_database_sidecars(snapshot_path)
            with suppress(OSError):
                snapshot_path.unlink()


def read_project_metadata() -> dict[str, object]:
    """Read the project identity and calculation selections from the database."""
    defaults: dict[str, object] = {
        "name": "",
        "standard": "G",
        "area_type": "I",
        "pathways": {key: False for key in PROJECT_PATHWAY_KEYS},
    }
    with connect() as connection:
        rows = connection.execute(
            f"select key, value from {PROJECT_METADATA_TABLE}"
        ).fetchall()
    values = {str(row["key"]): str(row["value"]) for row in rows}
    defaults["name"] = values.get("name", "")
    defaults["standard"] = values.get("standard", "G")
    defaults["area_type"] = values.get("area_type", "I")
    try:
        stored_pathways = json.loads(values.get("pathways", "{}"))
    except json.JSONDecodeError:
        stored_pathways = {}
    if isinstance(stored_pathways, dict):
        defaults["pathways"] = {
            key: stored_pathways.get(key) is True for key in PROJECT_PATHWAY_KEYS
        }
    return defaults


def write_project_metadata(
    *,
    name: str,
    standard: str,
    area_type: str,
    pathways: dict[str, bool],
) -> dict[str, object]:
    """Persist project metadata in the same SQLite file as assessment data."""
    normalized_pathways = {
        key: pathways.get(key) is True for key in PROJECT_PATHWAY_KEYS
    }
    values = {
        "name": name,
        "standard": standard,
        "area_type": area_type,
        "pathways": json.dumps(normalized_pathways, ensure_ascii=False),
    }
    with connect() as connection:
        for key, value in values.items():
            connection.execute(
                f"""
                insert into {PROJECT_METADATA_TABLE} (key, value)
                values (?, ?)
                on conflict(key) do update set value = excluded.value
                """,
                (key, value),
            )
    return read_project_metadata()


def _validate_project_database(database_path: Path) -> None:
    """Validate an imported project before it can replace the runtime database."""
    try:
        with sqlite3.connect(database_path) as connection:
            integrity = str(connection.execute("pragma integrity_check").fetchone()[0])
            if integrity != "ok" and not KNOWN_UNUSED_PAGE_WARNING.fullmatch(integrity):
                raise ValueError("项目文件数据库校验失败，文件可能已经损坏")
            version = int(connection.execute("pragma user_version").fetchone()[0])
            if version > DATABASE_SCHEMA_VERSION:
                raise ValueError(
                    f"项目文件版本 {version} 高于当前软件支持的版本 "
                    f"{DATABASE_SCHEMA_VERSION}"
                )
            tables = {
                row[0]
                for row in connection.execute(
                    "select name from sqlite_master where type = 'table'"
                )
            }
    except sqlite3.DatabaseError as error:
        raise ValueError("项目文件数据库校验失败，文件可能已经损坏") from error
    missing = sorted(PROJECT_TABLES - tables)
    if missing:
        missing_text = "、".join(missing[:5])
        raise ValueError(f"项目文件缺少必要的数据表：{missing_text}")


def replace_runtime_database(project_bytes: bytes) -> None:
    """Atomically replace the runtime database with a validated project file."""
    if not project_bytes:
        raise ValueError("项目文件为空")
    if len(project_bytes) > MAX_PROJECT_BYTES:
        raise ValueError(f"项目文件不能超过 {MAX_PROJECT_BYTES // (1024 * 1024)} MB")

    ensure_database()
    temporary_path: Path | None = None
    normalized_path: Path | None = None
    try:
        with _DATABASE_LOCK:
            with tempfile.NamedTemporaryFile(
                prefix="risk-project-import-",
                suffix=".db",
                dir=APP_DIR,
                delete=False,
            ) as temporary:
                temporary.write(project_bytes)
                temporary.flush()
                temporary_path = Path(temporary.name)
            temporary_path.chmod(0o600)
            _validate_project_database(temporary_path)
            _migrate_database(temporary_path, existing_database=False)
            # Both the runtime database and the imported temporary database may
            # use WAL mode.  Their sidecars must not survive an atomic swap.
            _checkpoint_database(RUNTIME_DB)
            normalized_path = _prepare_imported_database(temporary_path)
            _backup_database(RUNTIME_DB)
            _remove_database_sidecars(RUNTIME_DB)
            _remove_database_sidecars(temporary_path)
            with suppress(OSError):
                temporary_path.unlink()
            os.replace(normalized_path, RUNTIME_DB)
            normalized_path = None
            temporary_path = None
            with suppress(OSError):
                RUNTIME_DB.chmod(0o600)
    finally:
        if temporary_path is not None:
            _remove_database_sidecars(temporary_path)
            with suppress(OSError):
                temporary_path.unlink()
        if normalized_path is not None:
            _remove_database_sidecars(normalized_path)
            with suppress(OSError):
                normalized_path.unlink()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """统一的数据库连接上下文。

    这个封装替代了手写 try/commit/rollback/close：
    - 正常结束自动提交
    - 发生异常自动回滚
    - 最后总会关闭连接
    """
    database_path = ensure_database()
    connection = sqlite3.connect(database_path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("pragma busy_timeout = 15000")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
