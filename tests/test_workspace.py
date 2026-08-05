from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.app.composition import create_workspace_runtime
from genesis.app.kernel import GenesisSettings
from genesis.app.security import ApprovalState
from genesis.app.workspace import WorkspaceService


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_workspace_can_target_an_authorized_application_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "authorized-app"
            source_root.mkdir()
            (source_root / "app.py").write_text("print('app')\n", encoding="utf-8")
            runtime = create_workspace_runtime(
                GenesisSettings(data_dir=base / "state", workspace_dir=source_root)
            )
            await runtime.start()
            workspace = runtime.container.resolve("workspace", WorkspaceService)

            self.assertEqual(workspace.read_code("app.py").content, "print('app')\n")
            self.assertFalse((source_root / "memory").exists())
            self.assertTrue((base / "state" / "memory" / "genesis.db").is_file())
            await runtime.stop()

    async def test_workspace_connects_memory_files_terminal_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = create_workspace_runtime(GenesisSettings(data_dir=Path(temp_dir)))
            await runtime.start()
            workspace = runtime.container.resolve("workspace", WorkspaceService)

            workspace.add_message("neogen", "main", "user", "Continue")
            self.assertEqual(workspace.conversation("neogen", "main")[0].content, "Continue")

            write = workspace.request_file_write("neogen", "notes/plan.txt", "Milestone 012")
            with self.assertRaises(PermissionError):
                workspace.write_file("neogen", "notes/plan.txt", "Milestone 012", write.id)
            runtime.container.resolve("permissions").decide(write.id, approved=True)
            with self.assertRaises(PermissionError):
                workspace.write_file("neogen", "notes/plan.txt", "substituted", write.id)
            path = workspace.write_file("neogen", "notes/plan.txt", "Milestone 012", write.id)
            self.assertEqual(Path(path).read_text(), "Milestone 012")
            self.assertEqual(runtime.container.resolve("permissions").require(write.id).state, ApprovalState.CONSUMED)

            command = workspace.request_terminal("neogen", ("python", "-c", "print('ready')"))
            runtime.container.resolve("permissions").decide(command.id, approved=True)
            result = await workspace.run_terminal(
                "neogen", ("python", "-c", "print('ready')"), command.id
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout.strip(), "ready")
            self.assertIn("workspace", workspace.snapshot("neogen").capabilities)
            self.assertIn("coding", workspace.snapshot("neogen").capabilities)
            self.assertIn("research", workspace.snapshot("neogen").capabilities)
            self.assertIn("learning", workspace.snapshot("neogen").capabilities)
            self.assertIn("improvement", workspace.snapshot("neogen").capabilities)
            await runtime.stop()

    async def test_workspace_blocks_path_escape_and_cross_project_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = create_workspace_runtime(GenesisSettings(data_dir=Path(temp_dir)))
            await runtime.start()
            workspace = runtime.container.resolve("workspace", WorkspaceService)
            with self.assertRaises(PermissionError):
                workspace.request_file_write("neogen", "../escape.txt", "blocked")
            request = workspace.request_file_write("neogen", "safe.txt", "content")
            runtime.container.resolve("permissions").decide(request.id, approved=True)
            with self.assertRaises(PermissionError):
                workspace.write_file("another-project", "safe.txt", "content", request.id)
            await runtime.stop()


if __name__ == "__main__":
    unittest.main()
