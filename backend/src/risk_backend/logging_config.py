"""Configure a small rotating log for packaged-backend diagnostics."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from risk_backend.repositories.database import APP_DIR

LOG_PATH = APP_DIR / "risk-backend.log"
MAX_LOG_BYTES = 1_048_576
LOG_BACKUP_COUNT = 3


def configure_logging(log_path: Path = LOG_PATH) -> logging.Logger:
    """Configure the package logger once and return it."""
    logger = logging.getLogger("risk_backend")
    if any(
        getattr(handler, "_risk_studio_handler", False) for handler in logger.handlers
    ):
        return logger

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler._risk_studio_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
