"""HTTP integration tests for the approval-gated tablet workspace."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from genesis.tablet_server import create_tablet_server


class GuardedTabletWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.server = create_tablet_server(
            host="127.0.0.1",
            port=0,
            storage_path=root / "neogen.db",
            workspace_path=root / "workspace",
        )
        self.workspace = root / "workspace"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}/api/v1"
        self.post(
            "/auth/register",
            {
                "email": "guarded@example.com",
                "password": "guarded-password-123",
                "display_name": "Guarded User",
            },
        )
        session = self.post(
            "/auth/login",
            {"email": "guarded@example.com", "password": "guarded-password-123"},
        )
        self.token = session["token"]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server.RequestHandlerClass.kernel.close()
        asyncio.run(self.server.RequestHandlerClass.guarded_runtime.stop())
        self.temp.cleanup()

    def post(self, path: str, payload: dict[str, object], *, authenticated: bool = False):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def test_file_write_requires_exact_single_use_approval(self) -> None:
        action = {"path": "notes/plan.txt", "content": "Continue NeoGen"}
        approval = self.post(
            "/guarded/files/request-write", action, authenticated=True
        )

        with self.assertRaises(HTTPError) as unapproved:
            self.post(
                "/guarded/files/write",
                {**action, "approval_id": approval["id"]},
                authenticated=True,
            )
        self.assertEqual(unapproved.exception.code, 400)

        self.post(
            "/guarded/approvals/decide",
            {"approval_id": approval["id"], "approved": True},
            authenticated=True,
        )
        self.post(
            "/guarded/files/write",
            {**action, "approval_id": approval["id"]},
            authenticated=True,
        )
        self.assertEqual(
            (self.workspace / "notes" / "plan.txt").read_text(encoding="utf-8"),
            "Continue NeoGen",
        )

        with self.assertRaises(HTTPError) as reused:
            self.post(
                "/guarded/files/write",
                {**action, "approval_id": approval["id"]},
                authenticated=True,
            )
        self.assertEqual(reused.exception.code, 400)

    def test_terminal_approval_is_bound_to_exact_arguments(self) -> None:
        command = [sys.executable, "-c", "print('approved')"]
        approval = self.post(
            "/guarded/terminal/request", {"command": command}, authenticated=True
        )
        self.post(
            "/guarded/approvals/decide",
            {"approval_id": approval["id"], "approved": True},
            authenticated=True,
        )

        with self.assertRaises(HTTPError) as substituted:
            self.post(
                "/guarded/terminal/execute",
                {
                    "command": [sys.executable, "-c", "print('substituted')"],
                    "approval_id": approval["id"],
                },
                authenticated=True,
            )
        self.assertEqual(substituted.exception.code, 400)

        result = self.post(
            "/guarded/terminal/execute",
            {"command": command, "approval_id": approval["id"]},
            authenticated=True,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("approved", result["stdout"])


if __name__ == "__main__":
    unittest.main()
