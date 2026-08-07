"""Production hosting and public-boundary regression tests."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from genesis.production import create_production_server


class ProductionServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        data = Path(self.temp.name)
        self.environment = patch.dict(
            os.environ,
            {
                "HOST": "127.0.0.1",
                "PORT": "8080",
                "NEOGEN_DATA_DIR": str(data),
                "GENESIS_WORKSPACE_DIR": str(data / "workspace"),
                "NEOGEN_HTTPS": "1",
            },
            clear=False,
        )
        self.environment.start()
        with patch.dict(os.environ, {"PORT": "8080"}):
            self.server = create_production_server()
        self.server.server_close()
        # Bind an ephemeral test port after validating production configuration.
        os.environ["PORT"] = "0"
        with patch("genesis.production._positive_port", return_value=0):
            self.server = create_production_server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server.RequestHandlerClass.kernel.close()
        asyncio.run(self.server.RequestHandlerClass.guarded_runtime.stop())
        self.environment.stop()
        self.temp.cleanup()

    def test_health_and_security_headers(self) -> None:
        with urlopen(f"{self.base}/api/v1/health", timeout=5) as response:
            payload = json.loads(response.read())
            self.assertIn("status", payload)
            self.assertEqual(
                response.headers["Strict-Transport-Security"],
                "max-age=31536000; includeSubDomains",
            )
            self.assertIn("geolocation=()", response.headers["Permissions-Policy"])

    def test_direct_mutation_is_denied_before_authentication(self) -> None:
        request = Request(
            f"{self.base}/api/v1/terminal/execute",
            data=b'{"command":["python","--version"]}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as blocked:
            urlopen(request, timeout=5)
        self.assertEqual(blocked.exception.code, 403)
        payload = json.loads(blocked.exception.read())
        self.assertTrue(payload["approval_required"])

    def test_static_site_is_served(self) -> None:
        with urlopen(f"{self.base}/", timeout=5) as response:
            page = response.read().decode("utf-8")
        self.assertIn("Neo Genesis Afterlife", page)
        self.assertIn("Enter NeoGen", page)


if __name__ == "__main__":
    unittest.main()
