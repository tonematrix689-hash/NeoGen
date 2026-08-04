from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.app.coding import CodeChange, CodeWorkspaceTool, MISSING_FILE_DIGEST
from genesis.app.security import ApprovalState, PermissionEngine


class CodingToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_change_is_previewed_version_checked_checkpointed_and_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "workspace"
            root.mkdir()
            (root / "app.py").write_text("answer = 41\n", encoding="utf-8")
            permissions = PermissionEngine()
            coding = CodeWorkspaceTool(root, base / "checkpoints", permissions)
            await coding.start()

            inspected = coding.read("app.py")
            changes = (CodeChange("app.py", "answer = 42\n", inspected.sha256),)
            proposal = coding.propose("neogen", changes)
            self.assertIn("-answer = 41", proposal.diff)
            self.assertIn("+answer = 42", proposal.diff)

            with self.assertRaises(PermissionError):
                coding.apply("neogen", changes, proposal.approval.id)

            permissions.decide(proposal.approval.id, approved=True)
            checkpoint_id = coding.apply("neogen", changes, proposal.approval.id)
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "answer = 42\n")
            self.assertEqual(
                permissions.require(proposal.approval.id).state,
                ApprovalState.CONSUMED,
            )

            restore = coding.request_restore("neogen", checkpoint_id)
            permissions.decide(restore.id, approved=True)
            coding.restore("neogen", checkpoint_id, restore.id)
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "answer = 41\n")

    async def test_new_file_and_inventory_are_bounded_to_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            permissions = PermissionEngine()
            coding = CodeWorkspaceTool(base / "workspace", base / "checkpoints", permissions)
            await coding.start()

            new_file = coding.missing_file("src/new.py")
            self.assertEqual(new_file.sha256, MISSING_FILE_DIGEST)
            changes = (CodeChange("src/new.py", "print('safe')\n", new_file.sha256),)
            proposal = coding.propose("neogen", changes)
            permissions.decide(proposal.approval.id, approved=True)
            coding.apply("neogen", changes, proposal.approval.id)

            self.assertEqual(coding.inventory()[0].path, "src/new.py")
            with self.assertRaises(PermissionError):
                coding.read("../outside.py")

    async def test_stale_source_and_substituted_changes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "workspace"
            root.mkdir()
            source = root / "main.py"
            source.write_text("version = 1\n", encoding="utf-8")
            permissions = PermissionEngine()
            coding = CodeWorkspaceTool(root, base / "checkpoints", permissions)
            await coding.start()

            inspected = coding.read("main.py")
            changes = (CodeChange("main.py", "version = 2\n", inspected.sha256),)
            proposal = coding.propose("neogen", changes)
            permissions.decide(proposal.approval.id, approved=True)
            source.write_text("version = 3\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed after inspection"):
                coding.apply("neogen", changes, proposal.approval.id)

            current = coding.read("main.py")
            exact = (CodeChange("main.py", "version = 4\n", current.sha256),)
            exact_proposal = coding.propose("neogen", exact)
            permissions.decide(exact_proposal.approval.id, approved=True)
            substituted = (CodeChange("main.py", "version = 999\n", current.sha256),)
            with self.assertRaises(PermissionError):
                coding.apply("neogen", substituted, exact_proposal.approval.id)

    async def test_inventory_ignores_symlinked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "workspace"
            root.mkdir()
            outside = base / "secret.txt"
            outside.write_text("do not inventory", encoding="utf-8")
            link = root / "linked.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("Symlinks are unavailable on this platform")
            coding = CodeWorkspaceTool(root, base / "checkpoints", PermissionEngine())
            await coding.start()

            self.assertEqual(coding.inventory(), ())
            with self.assertRaises(PermissionError):
                coding.read("linked.txt")


if __name__ == "__main__":
    unittest.main()
