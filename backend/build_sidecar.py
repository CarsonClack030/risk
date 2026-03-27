from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "bin"
BUILD_DIR = ROOT / "build"
ENTRY = ROOT / "main.py"
TEMPLATE_DB = ROOT / "src" / "risk_backend" / "resources" / "template.db"
ADD_DATA_ARG = f"{TEMPLATE_DB}{os.pathsep}risk_backend/resources"


def target_triple() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    if os.name == "nt":
        if machine in {"arm64", "aarch64"}:
            return "aarch64-pc-windows-msvc"
        return "x86_64-pc-windows-msvc"
    if machine in {"arm64", "aarch64"}:
        return "aarch64-unknown-linux-gnu"
    return "x86_64-unknown-linux-gnu"


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    binary_name = f"risk-backend-{target_triple()}"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        binary_name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / "work"),
        "--specpath",
        str(BUILD_DIR / "spec"),
        "--paths",
        str(ROOT / "src"),
        "--add-data",
        ADD_DATA_ARG,
        str(ENTRY),
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
