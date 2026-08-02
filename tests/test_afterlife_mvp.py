"""Integration tests for the dependency-free Afterlife MVP server."""

from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from genesis.apps.afterlife.server import build_server, vera_reply


class AfterlifeMVPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = build_server("127.0.0.1", 0)
        cls.host, cls.port = cls.server.server_address
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://{cls.host}:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path: str) -> tuple[int, str, bytes]:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            return response.status, response.headers["content-type"], response.read()

    def test_landing_page(self) -> None:
        status, content_type, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"AFTERLIFE NEOGENESIS", body)

    def test_dashboard_page(self) -> None:
        status, _, body = self.get("/dashboard")
        self.assertEqual(status, 200)
        self.assertIn(b"VERA", body)
        self.assertIn(b"Avatar Forge", body)

    def test_health_endpoint(self) -> None:
        status, content_type, body = self.get("/health")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "healthy")

    def test_state_endpoint(self) -> None:
        status, _, body = self.get("/api/state")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["companion"], "VERA")
        self.assertGreaterEqual(payload["neo_balance"], 0)

    def test_vera_endpoint(self) -> None:
        request = Request(
            f"{self.base_url}/api/vera",
            data=json.dumps({"message": "Help with my avatar"}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["mode"], "deterministic-mvp")
        self.assertIn("avatar", payload["reply"].lower())

    def test_invalid_vera_request(self) -> None:
        request = Request(
            f"{self.base_url}/api/vera",
            data=json.dumps({"message": 42}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 400)

    def test_deterministic_guidance(self) -> None:
        self.assertEqual(vera_reply("wallet"), vera_reply("wallet"))
        self.assertIn("approval", vera_reply("permissions").lower())


if __name__ == "__main__":
    unittest.main()
