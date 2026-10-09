"""Configure a small rotating log for packaged-backend diagnostics."""

from __future__ import annotations

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from risk_backend.repositories.database import APP_DIR, APP_NAME

LOG_PATH = APP_DIR / "risk-backend.log"
MAX_LOG_BYTES = 1_048_576
LOG_BACKUP_COUNT = 3


def _candidate_log_paths(primary: Path) -> list[Path]:
    """Return writable log locations in priority order.

    The roaming application-data directory is the normal location on Windows.
    Some packaged installations, however, run with a restricted profile or
    security software temporarily locking that directory.  Keep a local-data
    and temp fallback so a user can still find the real backend exception.
    """
    candidates = [primary]
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / APP_NAME / LOG_PATH.name)
    candidates.append(Path(tempfile.gettempdir()) / APP_NAME / LOG_PATH.name)

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def configure_logging(log_path: Path | None = None) -> logging.Logger:
    """Configure the package logger once and return it.

    File logging is deliberately best-effort: a logging failure must never
    stop the desktop application from starting.  If the primary location is
    unavailable, the logger tries local app data and then the system temp
    directory.
    """
    logger = logging.getLogger("risk_backend")
    if any(
        getattr(handler, "_risk_studio_handler", False) for handler in logger.handlers
    ):
        return logger

    primary = log_path or LOG_PATH
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    failures: list[str] = []
    for candidate in _candidate_log_paths(primary):
        handler: RotatingFileHandler | None = None
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                candidate,
                maxBytes=MAX_LOG_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler._risk_studio_handler = True  # type: ignore[attr-defined]
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger._risk_studio_log_path = str(candidate)  # type: ignore[attr-defined]
            break
        except OSError as error:
            failures.append(f"{candidate}: {error}")
            if handler is not None:
                handler.close()
    else:
        # GUI builds do not have a visible console, but keeping a stream
        # handler still helps development builds and never blocks startup.
        handler = logging.StreamHandler()
        handler._risk_studio_handler = True  # type: ignore[attr-defined]
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger._risk_studio_log_path = "无法创建文件日志"  # type: ignore[attr-defined]

    logger.setLevel(logging.INFO)
    logger.propagate = False
    if failures:
        logger.warning("Some backend log locations were unavailable: %s", " | ".join(failures))
    return logger


def configured_log_path() -> str:
    """Return the path currently used for backend diagnostics."""
    logger = logging.getLogger("risk_backend")
    return str(getattr(logger, "_risk_studio_log_path", LOG_PATH))
