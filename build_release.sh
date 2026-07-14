#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.cargo/bin:$PATH"
TARGET="${1:-app}"

cd "$ROOT_DIR"

echo "[1/4] Building Python sidecar"
python3 backend/build_sidecar.py

echo "[2/4] Building frontend"
npm run build:web

echo "[3/4] Building macOS bundle ($TARGET)"
if [[ "$TARGET" != "app" && "$TARGET" != "dmg" ]]; then
  echo "Unsupported target: $TARGET"
  echo "Usage: ./build_release.sh [app|dmg]"
  exit 1
fi
npm run tauri -- build -b "$TARGET"

echo "[4/4] Release build ready"
if [[ "$TARGET" == "dmg" ]]; then
  echo "DMG: $ROOT_DIR/src-tauri/target/release/bundle/dmg"
  echo "Release binary: $ROOT_DIR/src-tauri/target/release/risk_studio"
else
  echo "App: $ROOT_DIR/src-tauri/target/release/bundle/macos/Risk Studio.app"
fi
echo "Sidecar: $ROOT_DIR/backend/bin"
