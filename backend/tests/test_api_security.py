from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection

from risk_backend.api_server import RequestHandler, RiskHTTPServer


class FakeBackend:
    def __init__(self) -> None:
        self.admin_writes = 0
        self.session_token = "admin-session"

    @staticmethod
    def health() -> dict[str, object]:
        return {"status": "ok"}

    def validate_admin_session(self, token: str) -> str | None:
        return "admin" if token == self.session_token else None

    @staticmethod
    def login(_payload: dict[str, object]) -> dict[str, object]:
        return {"success": False, "username": "", "token": ""}

    def add_pollutant(self, _payload: dict[str, object]) -> dict[str, object]:
        self.admin_writes += 1
        return {"total": self.admin_writes}


class ApiSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeBackend()
        RequestHandler.backend = self.backend
        RequestHandler.api_token = "desktop-api-token"
        RequestHandler.shutdown_token = "shutdown-token"
        RequestHandler._login_failures.clear()
        self.server = RiskHTTPServer(("127.0.0.1", 0), RequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        RequestHandler.api_token = ""

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
        request_headers = dict(headers or {})
        request_headers["Content-Length"] = str(len(body))
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {key: value for key, value in response.getheaders()}
        connection.close()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, payload, response_headers

    def test_api_rejects_missing_desktop_token(self) -> None:
        status, payload, _headers = self.request("GET", "/api/health")

        self.assertEqual(status, 403)
        self.assertIn("error", payload)

    def test_api_accepts_current_desktop_token(self) -> None:
        status, payload, _headers = self.request(
            "GET",
            "/api/health",
            headers={"X-Risk-Api-Token": "desktop-api-token"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_admin_write_requires_session_even_with_desktop_token(self) -> None:
        body = json.dumps({"name": "test"}).encode()
        status, _payload, _headers = self.request(
            "POST",
            "/api/admin/pollutants",
            body=body,
            headers={
                "Content-Type": "application/json",
                "X-Risk-Api-Token": "desktop-api-token",
            },
        )

        self.assertEqual(status, 401)
        self.assertEqual(self.backend.admin_writes, 0)

    def test_admin_write_accepts_valid_session(self) -> None:
        body = json.dumps({"name": "test"}).encode()
        status, payload, _headers = self.request(
            "POST",
            "/api/admin/pollutants",
            body=body,
            headers={
                "Authorization": "Bearer admin-session",
                "Content-Type": "application/json",
                "X-Risk-Api-Token": "desktop-api-token",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 1)

    def test_untrusted_origin_does_not_receive_cors_permission(self) -> None:
        status, _payload, headers = self.request(
            "OPTIONS",
            "/api/health",
            headers={
                "Origin": "https://example.test",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_trusted_origin_is_reflected_without_wildcard(self) -> None:
        status, _payload, headers = self.request(
            "OPTIONS",
            "/api/health",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(status, 204)
        self.assertEqual(
            headers["Access-Control-Allow-Origin"], "http://localhost:1420"
        )

    def test_oversized_json_body_is_rejected_before_reading(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
        connection.putrequest("POST", "/api/workspace/add")
        connection.putheader("X-Risk-Api-Token", "desktop-api-token")
        connection.putheader("Content-Length", str(2 * 1024 * 1024 + 1))
        connection.endheaders()
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()

        self.assertEqual(response.status, 413)
        self.assertIn("超过限制", payload["error"])

    def test_repeated_login_failures_are_throttled(self) -> None:
        body = json.dumps({"username": "admin", "password": "wrong"}).encode()
        statuses = []
        for _ in range(6):
            status, _payload, _headers = self.request(
                "POST",
                "/api/auth/login",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Risk-Api-Token": "desktop-api-token",
                },
            )
            statuses.append(status)

        self.assertEqual(statuses[:5], [200] * 5)
        self.assertEqual(statuses[5], 429)


if __name__ == "__main__":
    unittest.main()
