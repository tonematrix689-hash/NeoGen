from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from genesis.app.coding import CodeChange, CodeWorkspaceTool
from genesis.app.improvement import ImprovementState, SelfImprovementService
from genesis.app.learning import LearningService
from genesis.app.memory import MemoryService
from genesis.app.security import PermissionEngine
from genesis.app.tools import TerminalTool


class ImprovementServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "workspace"
        self.root.mkdir()
        self.permissions = PermissionEngine()
        self.memory = MemoryService(base / "memory.db")
        self.learning = LearningService(base / "learning.db")
        self.coding = CodeWorkspaceTool(self.root, base / "checkpoints", self.permissions)
        self.terminal = TerminalTool(self.root, self.permissions)
        self.improvement = SelfImprovementService(
            self.permissions,
            self.coding,
            self.terminal,
            self.memory,
            self.learning,
        )
        for service in (self.memory, self.learning, self.coding, self.terminal, self.improvement):
            await service.start()

    async def asyncTearDown(self) -> None:
        for service in (self.improvement, self.terminal, self.coding, self.learning, self.memory):
            await service.stop()
        self.temporary.cleanup()

    def approve_plan(self, plan) -> None:
        self.permissions.decide(plan.code_proposal.approval.id, approved=True)
        for step in plan.verification_steps:
            self.permissions.decide(step.approval.id, approved=True)

    async def test_approved_improvement_edits_verifies_and_learns(self) -> None:
        source = self.root / "app.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        inspected = self.coding.read("app.py")
        plan = self.improvement.prepare(
            "neogen",
            "Improve the value",
            (CodeChange("app.py", "VALUE = 2\n", inspected.sha256),),
            ((sys.executable, "-c", "import app; assert app.VALUE == 2"),),
            strategy="verified-edit",
            source_urls=("https://docs.python.org/3/",),
        )
        self.approve_plan(plan)

        result = await self.improvement.execute(plan)

        self.assertEqual(result.state, ImprovementState.SUCCEEDED)
        self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 2\n")
        self.assertIsNotNone(result.checkpoint_id)
        self.assertEqual(
            self.learning.outcomes("neogen", "self_improvement")[0].reward,
            1.0,
        )

    async def test_failed_verification_automatically_restores_checkpoint(self) -> None:
        source = self.root / "app.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        inspected = self.coding.read("app.py")
        plan = self.improvement.prepare(
            "neogen",
            "Try a change that fails verification",
            (CodeChange("app.py", "VALUE = 2\n", inspected.sha256),),
            ((sys.executable, "-c", "raise SystemExit(7)"),),
            strategy="failed-edit",
        )
        self.approve_plan(plan)

        result = await self.improvement.execute(plan)

        self.assertEqual(result.state, ImprovementState.ROLLED_BACK)
        self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 1\n")
        self.assertIn("code 7", result.error or "")
        self.assertEqual(
            self.learning.outcomes("neogen", "self_improvement")[0].reward,
            0.0,
        )

    async def test_execution_refuses_partially_approved_plan(self) -> None:
        source = self.root / "app.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        inspected = self.coding.read("app.py")
        plan = self.improvement.prepare(
            "neogen",
            "Do not execute without every approval",
            (CodeChange("app.py", "VALUE = 2\n", inspected.sha256),),
            ((sys.executable, "-c", "print('verify')"),),
        )
        self.permissions.decide(plan.code_proposal.approval.id, approved=True)

        with self.assertRaises(PermissionError):
            await self.improvement.execute(plan)
        self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 1\n")

    async def test_recovery_does_not_overwrite_source_changed_during_verification(self) -> None:
        source = self.root / "app.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        inspected = self.coding.read("app.py")
        plan = self.improvement.prepare(
            "neogen",
            "Preserve a concurrent source edit",
            (CodeChange("app.py", "VALUE = 2\n", inspected.sha256),),
            (
                (
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('app.py').write_text('VALUE = 99\\n'); raise SystemExit(7)",
                ),
            ),
        )
        self.approve_plan(plan)

        result = await self.improvement.execute(plan)

        self.assertEqual(result.state, ImprovementState.FAILED)
        self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 99\n")
        self.assertIn("recovery conflict", result.error or "")


if __name__ == "__main__":
    unittest.main()
