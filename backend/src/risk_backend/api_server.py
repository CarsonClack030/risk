"""Local HTTP transport for the Risk Studio application service."""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from risk_backend.application import RiskBackend
from risk_backend.logging_config import configure_logging

EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
IMPORT_PATHS = {"/api/workspace/import-file", "/api/workspace/import-excel"}
MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
MAX_IMPORT_BODY_BYTES = 25 * 1024 * 1024
ALLOWED_ORIGINS = {
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
}
LOGGER = logging.getLogger("risk_backend.api")
LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_FAILURES = 5


class PayloadTooLarge(ValueError):
    """Raised before reading a request body that exceeds the route limit."""


class RiskHTTPServer(ThreadingHTTPServer):
    """Do not keep the desktop process alive for abandoned request threads."""

    daemon_threads = True


def first_query(params: dict[str, list[str]], key: str) -> str:
    """Return the first parsed query value, or an empty string when absent."""
    values = params.get(key)
    return values[0] if values else ""


class RequestHandler(BaseHTTPRequestHandler):
    """Translate HTTP requests into calls on :class:`RiskBackend`."""

    backend: RiskBackend
    shutdown_token = ""
    api_token = ""
    _login_failures: dict[str, tuple[int, float]] = {}
    _login_lock = threading.Lock()

    def do_OPTIONS(self) -> None:
        if not self._origin_is_allowed():
            self._send_error("不允许的请求来源", HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if not self._require_api_token():
            return
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path == "/api/health":
                self._send_json(self.backend.health())
            elif parsed.path == "/api/catalog":
                self._send_json(
                    self.backend.list_catalog(first_query(params, "keyword"))
                )
            elif parsed.path == "/api/workspace":
                self._send_json(self.backend.list_workspace())
            elif parsed.path == "/api/workspace/import-template":
                self._send_binary(
                    self.backend.export_workspace_import_template(),
                    EXCEL_CONTENT_TYPE,
                    "污染物导入模板.xlsx",
                )
            elif parsed.path == "/api/parameters":
                self._send_json(self.backend.list_parameters())
            elif parsed.path == "/api/results":
                self._send_json(self.backend.list_results())
            else:
                self._send_not_found()
        except Exception as exc:
            self._handle_exception(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path == "/api/shutdown":
                self._handle_shutdown()
                return
            if not self._require_api_token():
                return
            if parsed.path in IMPORT_PATHS:
                self._send_json(
                    self.backend.import_workspace_file(
                        self._read_body(MAX_IMPORT_BODY_BYTES),
                        filename=first_query(params, "filename"),
                        content_type=self.headers.get("Content-Type", ""),
                    )
                )
                return

            payload = self._read_json()
            if parsed.path == "/api/workspace/add":
                self._send_json(
                    self.backend.add_workspace_item(int(payload["pollutant_id"]))
                )
            elif parsed.path == "/api/workspace/reset":
                self._send_json(self.backend.reset_workspace())
            elif parsed.path == "/api/parameters/reset":
                self._send_json(self.backend.reset_parameters())
            elif parsed.path == "/api/calculate":
                self._send_json(self.backend.calculate(payload))
            elif parsed.path == "/api/results/export":
                self._send_binary(
                    self.backend.export_results(),
                    EXCEL_CONTENT_TYPE,
                    "risk-results.xlsx",
                )
            elif parsed.path == "/api/auth/login":
                if not self._login_allowed():
                    return
                result = self.backend.login(payload)
                if result.get("success") is True:
                    self._clear_login_failures()
                else:
                    self._record_login_failure()
                self._send_json(result)
            elif parsed.path == "/api/auth/password":
                username = self._require_admin()
                if username is not None:
                    self._send_json(self.backend.update_password(payload, username))
            elif parsed.path == "/api/auth/logout":
                token = self._require_admin_token()
                if token is not None:
                    self._send_json(self.backend.logout(token))
            elif parsed.path == "/api/admin/pollutants":
                if self._require_admin() is not None:
                    self._send_json(self.backend.add_pollutant(payload))
            else:
                self._send_not_found()
        except Exception as exc:
            self._handle_exception(exc)

    def do_PUT(self) -> None:
        if not self._require_api_token():
            return
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/workspace/concentrations":
                items = payload.get("items", [])
                if not isinstance(items, list):
                    raise ValueError("浓度数据必须是列表")
                self._send_json(self.backend.update_concentrations(items))
            elif parsed.path == "/api/parameters":
                groups = payload.get("groups", [])
                if not isinstance(groups, list):
                    raise ValueError("参数分组必须是列表")
                self._send_json(self.backend.save_parameters(groups))
            elif parsed.path.startswith("/api/admin/pollutants/"):
                if self._require_admin() is not None:
                    pollutant_id = int(parsed.path.rsplit("/", 1)[-1])
                    self._send_json(
                        self.backend.update_pollutant(pollutant_id, payload)
                    )
            else:
                self._send_not_found()
        except Exception as exc:
            self._handle_exception(exc)

    def do_DELETE(self) -> None:
        if not self._require_api_token():
            return
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path.startswith("/api/workspace/"):
                workspace_number = int(parsed.path.rsplit("/", 1)[-1])
                self._send_json(self.backend.remove_workspace_item(workspace_number))
            elif parsed.path.startswith("/api/admin/pollutants/"):
                if self._require_admin() is not None:
                    pollutant_id = int(parsed.path.rsplit("/", 1)[-1])
                    self._send_json(
                        self.backend.delete_pollutant(
                            pollutant_id,
                            first_query(params, "keyword"),
                        )
                    )
            else:
                self._send_not_found()
        except Exception as exc:
            self._handle_exception(exc)

    def _handle_shutdown(self) -> None:
        supplied_token = self.headers.get("X-Risk-Shutdown-Token", "")
        if not self.shutdown_token or not hmac.compare_digest(
            supplied_token,
            self.shutdown_token,
        ):
            self._send_error("无权关闭后端服务", HTTPStatus.FORBIDDEN)
            return

        self._send_json({"status": "stopping"})
        # Calling shutdown on the request thread would deadlock serve_forever.
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _require_api_token(self) -> bool:
        if not self.api_token:
            return True
        supplied_token = self.headers.get("X-Risk-Api-Token", "")
        if hmac.compare_digest(supplied_token, self.api_token):
            return True
        self._send_error("无权访问本地后端服务", HTTPStatus.FORBIDDEN)
        return False

    def _require_admin_token(self) -> str | None:
        authorization = self.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            self._send_error("管理员登录已失效，请重新登录", HTTPStatus.UNAUTHORIZED)
            return None
        username = self.backend.validate_admin_session(token)
        if username is None:
            self._send_error("管理员登录已失效，请重新登录", HTTPStatus.UNAUTHORIZED)
            return None
        return token

    def _require_admin(self) -> str | None:
        token = self._require_admin_token()
        return self.backend.validate_admin_session(token) if token is not None else None

    def _login_client_key(self) -> str:
        return str(self.client_address[0])

    def _login_allowed(self) -> bool:
        now = time.monotonic()
        key = self._login_client_key()
        with self._login_lock:
            failures, started_at = self._login_failures.get(key, (0, now))
            if now - started_at >= LOGIN_WINDOW_SECONDS:
                self._login_failures.pop(key, None)
                return True
            if failures >= MAX_LOGIN_FAILURES:
                self._send_error(
                    "登录失败次数过多，请 5 分钟后再试",
                    HTTPStatus.TOO_MANY_REQUESTS,
                )
                return False
        return True

    def _record_login_failure(self) -> None:
        now = time.monotonic()
        key = self._login_client_key()
        with self._login_lock:
            failures, started_at = self._login_failures.get(key, (0, now))
            if now - started_at >= LOGIN_WINDOW_SECONDS:
                failures, started_at = 0, now
            self._login_failures[key] = (failures + 1, started_at)

    def _clear_login_failures(self) -> None:
        with self._login_lock:
            self._login_failures.pop(self._login_client_key(), None)

    def _read_json(self) -> dict[str, object]:
        raw = self._read_body()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    def _read_body(self, max_bytes: int = MAX_JSON_BODY_BYTES) -> bytes:
        raw_content_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_content_length)
        except ValueError:
            raise ValueError("Content-Length 不是合法整数") from None
        if content_length < 0:
            raise ValueError("Content-Length 不能小于 0")
        if content_length > max_bytes:
            self.close_connection = True
            raise PayloadTooLarge(
                f"上传内容超过限制（最大 {max_bytes // (1024 * 1024)} MB）"
            )
        return self.rfile.read(content_length) if content_length > 0 else b""

    def _send_json(
        self,
        payload: dict[str, object],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_binary(self, payload: bytes, content_type: str, filename: str) -> None:
        ascii_filename = filename.encode("ascii", "ignore").decode("ascii").strip()
        ascii_filename = ascii_filename or "download.bin"
        self.send_response(HTTPStatus.OK)
        self._write_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(filename)}",
        )
        self.end_headers()
        self.wfile.write(payload)

    def _send_not_found(self) -> None:
        self._send_error("未找到接口", HTTPStatus.NOT_FOUND)

    def _send_error(
        self,
        message: str,
        status: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ) -> None:
        self._send_json({"error": message}, status=status)

    def _handle_exception(self, exc: Exception) -> None:
        if isinstance(exc, PayloadTooLarge):
            self._send_error(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        if isinstance(exc, (ValueError, KeyError, json.JSONDecodeError, UnicodeError)):
            message = (
                f"缺少请求字段：{exc.args[0]}"
                if isinstance(exc, KeyError)
                else str(exc)
            )
            self._send_error(message, HTTPStatus.BAD_REQUEST)
            return
        LOGGER.exception("Unhandled backend request error")
        self._send_error(
            "后端处理失败，请查看运行日志", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    def _origin_is_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        return not origin or origin in ALLOWED_ORIGINS

    def _write_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Risk-Api-Token",
        )
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )

    def log_message(self, message_format: str, *args: object) -> None:
        """Write request metadata to the rotating log, never request bodies."""
        LOGGER.info("%s - %s", self.address_string(), message_format % args)


def run(
    host: str = "127.0.0.1",
    port: int = 38911,
    shutdown_token: str = "",
    api_token: str = "",
) -> None:
    configure_logging()
    RequestHandler.backend = RiskBackend()
    RequestHandler.shutdown_token = shutdown_token
    RequestHandler.api_token = api_token
    with RequestHandler._login_lock:
        RequestHandler._login_failures.clear()
    server = RiskHTTPServer((host, port), RequestHandler)
    LOGGER.info("Backend listening on http://%s:%s", host, port)
    print(f"risk-backend listening on http://{host}:{port}")
    try:
        server.serve_forever(poll_interval=0.05)
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()
        LOGGER.info("Backend stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Risk Studio backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=38911)
    parser.add_argument(
        "--shutdown-token", default=os.environ.get("RISK_SHUTDOWN_TOKEN", "")
    )
    parser.add_argument("--api-token", default=os.environ.get("RISK_API_TOKEN", ""))
    args = parser.parse_args()
    run(args.host, args.port, args.shutdown_token, args.api_token)


if __name__ == "__main__":
    main()
