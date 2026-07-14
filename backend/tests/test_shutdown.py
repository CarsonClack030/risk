from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from risk_backend.api_server import RequestHandler


class ShutdownEndpointTests(unittest.TestCase):
    """验证桌面壳只能使用本次启动令牌关闭后端。"""

    def setUp(self) -> None:
        RequestHandler.shutdown_token = "test-shutdown-token"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()

    def tearDown(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def post_shutdown(self, token: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=1)
        connection.request(
            "POST",
            "/api/shutdown",
            headers={"X-Risk-Shutdown-Token": token, "Content-Length": "0"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, payload

    def test_invalid_token_cannot_stop_backend(self) -> None:
        status, payload = self.post_shutdown("wrong-token")

        self.assertEqual(status, 403)
        self.assertIn("error", payload)
        self.assertTrue(self.thread.is_alive())

    def test_valid_token_stops_backend(self) -> None:
        status, payload = self.post_shutdown("test-shutdown-token")

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "stopping")
        self.thread.join(timeout=1)
        self.assertFalse(self.thread.is_alive())
