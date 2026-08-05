"""Tests for governed Git repository access."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from genesis.app.repository import RepositoryService
from genesis.app.security import PermissionEngine


class RepositoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(("git", "init", "-b", "main"), cwd=self.root, check=True, capture_output=True)
        subprocess.run(("git", "config", "user.name", "NeoGen Tests"), cwd=self.root, check=True)
        subprocess.run(
            ("git", "config", "user.email", "neogen-tests@example.invalid"),
            cwd=self.root,
            check=True,
        )
        (self.root / "README.md").write_text("# NeoGen\n", encoding="utf-8")
        subprocess.run(("git", "add", "README.md"), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-m", "Initial"), cwd=self.root, check=True, capture_output=True)
        self.permissions = PermissionEngine()
        self.repository = RepositoryService(self.root, self.permissions)
        await self.repository.start()

    async def asyncTearDown(self) -> None:
        await self.repository.stop()
        self.temp.cleanup()

    async def test_inspection_reports_checkout_without_exposing_remote_urls(self) -> None:
        subprocess.run(
            ("git", "remote", "add", "origin", "https://token@example.invalid/owner/repo.git"),
            cwd=self.root,
            check=True,
        )
        snapshot = self.repository.snapshot()

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.branch, "main")
        self.assertEqual(snapshot.remotes, ("origin",))
        self.assertNotIn("token", repr(snapshot))
        self.assertIn("Initial", self.repository.log())

    async def test_mutation_requires_exact_single_use_approval(self) -> None:
        arguments = ("switch", "-c", "agent/repository-access")
        approval = self.repository.request("neogen", arguments)

        with self.assertRaises(PermissionError):
            await self.repository.run("neogen", arguments, approval.id)

        self.permissions.decide(approval.id, approved=True)
        with self.assertRaises(PermissionError):
            await self.repository.run(
                "neogen", ("switch", "-c", "substituted"), approval.id
            )

        result = await self.repository.run("neogen", arguments, approval.id)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(self.repository.snapshot().branch, "agent/repository-access")

        with self.assertRaises(PermissionError):
            await self.repository.run("neogen", arguments, approval.id)


if __name__ == "__main__":
    unittest.main()
