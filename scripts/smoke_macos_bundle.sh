#!/usr/bin/env bash

# 对最终 DMG 做一次接近真实用户环境的冒烟测试。
# 这一步专门防止“应用包能生成、界面能打开，但 Python sidecar 无法启动”的问题。

set -euo pipefail

DMG_PATH="${1:-src-tauri/target/release/bundle/dmg/Risk Studio_1.1.0_aarch64.dmg}"
MOUNT_DIR="$(mktemp -d /tmp/risk-studio-smoke.XXXXXX)"
BACKEND_PID=""
BACKEND_LOG="$(mktemp /tmp/risk-studio-backend.XXXXXX.log)"

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  hdiutil detach "$MOUNT_DIR" >/dev/null 2>&1 || true
  rm -f "$BACKEND_LOG"
  rmdir "$MOUNT_DIR" 2>/dev/null || true
}
trap cleanup EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This smoke test must run on macOS."
  exit 1
fi

if [[ ! -f "$DMG_PATH" ]]; then
  echo "DMG not found: $DMG_PATH"
  exit 1
fi

hdiutil verify "$DMG_PATH" >/dev/null
hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT_DIR" "$DMG_PATH" >/dev/null

APP_PATH="$MOUNT_DIR/Risk Studio.app"
BACKEND_PATH="$APP_PATH/Contents/MacOS/risk-backend"

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
codesign -d --entitlements - "$BACKEND_PATH" 2>&1 \
  | grep -q "com.apple.security.cs.disable-library-validation"

# 使用临时空闲端口，避免测试机上已有的软件影响本次检查。
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
"$BACKEND_PATH" --host 127.0.0.1 --port "$PORT" >"$BACKEND_LOG" 2>&1 &
BACKEND_PID="$!"

for _ in {1..30}; do
  if curl --silent --fail "http://127.0.0.1:$PORT/api/health" \
    | grep -q '"status": "ok"'; then
    echo "macOS bundle smoke test passed on port $PORT."
    exit 0
  fi

  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Packaged backend exited before becoming healthy."
    cat "$BACKEND_LOG"
    exit 1
  fi
  sleep 1
done

echo "Packaged backend did not become healthy within 30 seconds."
cat "$BACKEND_LOG"
exit 1
