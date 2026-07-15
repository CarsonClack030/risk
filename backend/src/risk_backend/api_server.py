"""Local HTTP transport for the Risk Studio application service."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from risk_backend.application import RiskBackend

EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
IMPORT_PATHS = {"/api/workspace/import-file", "/api/workspace/import-excel"}


def first_query(params: dict[str, list[str]], key: str) -> str:
    """Return the first parsed query value, or an empty string when absent."""
    values = params.get(key)
    return values[0] if values else ""


class RequestHandler(BaseHTTPRequestHandler):
    """Translate HTTP requests into calls on :class:`RiskBackend`."""

    backend = RiskBackend()
    shutdown_token = ""

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
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
            self._send_error(str(exc))

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path == "/api/shutdown":
                self._handle_shutdown()
                return
            if parsed.path in IMPORT_PATHS:
                self._send_json(
                    self.backend.import_workspace_file(
                        self._read_body(),
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
                self._send_json(self.backend.login(payload))
            elif parsed.path == "/api/auth/password":
                self._send_json(self.backend.update_password(payload))
            elif parsed.path == "/api/admin/pollutants":
                self._send_json(self.backend.add_pollutant(payload))
            else:
                self._send_not_found()
        except Exception as exc:
            self._send_error(str(exc))

    def do_PUT(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/workspace/concentrations":
                self._send_json(
                    self.backend.update_concentrations(payload.get("items", []))
                )
            elif parsed.path == "/api/parameters":
                self._send_json(self.backend.save_parameters(payload.get("groups", [])))
            elif parsed.path.startswith("/api/admin/pollutants/"):
                pollutant_id = int(parsed.path.rsplit("/", 1)[-1])
                self._send_json(self.backend.update_pollutant(pollutant_id, payload))
            else:
                self._send_not_found()
        except Exception as exc:
            self._send_error(str(exc))

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path.startswith("/api/workspace/"):
                workspace_number = int(parsed.path.rsplit("/", 1)[-1])
                self._send_json(self.backend.remove_workspace_item(workspace_number))
            elif parsed.path.startswith("/api/admin/pollutants/"):
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
            self._send_error(str(exc))

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

    def _read_json(self) -> dict[str, object]:
        raw = self._read_body()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
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

    def _write_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )

    def log_message(self, _format: str, *_args: object) -> None:
        """Suppress the noisy default request log in the desktop application."""


def run(host: str = "127.0.0.1", port: int = 38911, shutdown_token: str = "") -> None:
    RequestHandler.shutdown_token = shutdown_token
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"risk-backend listening on http://{host}:{port}")
    try:
        server.serve_forever(poll_interval=0.05)
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Risk Studio backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=38911)
    parser.add_argument(
        "--shutdown-token", default=os.environ.get("RISK_SHUTDOWN_TOKEN", "")
    )
    args = parser.parse_args()
    run(args.host, args.port, args.shutdown_token)


if __name__ == "__main__":
    main()
