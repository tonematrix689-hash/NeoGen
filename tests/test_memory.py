from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.app.kernel.runtime import GenesisRuntime, ServiceDescriptor
from genesis.app.kernel.settings import GenesisSettings
from genesis.app.memory import MemoryService


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_memory_and_conversation_persist_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "memory.db"
            first = MemoryService(database)
            await first.start()
            first.remember("neogen", "Build the post-login workspace.", category="decision")
            first.add_turn("neogen", "main", "user", "Continue to continue")
            await first.stop()

            second = MemoryService(database)
            await second.start()
            self.assertEqual(second.search("neogen", "post-login")[0].category, "decision")
            self.assertEqual(second.conversation("neogen", "main")[0].role, "user")
            await second.stop()

    async def test_memory_runs_as_kernel_managed_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = GenesisSettings(data_dir=Path(temp_dir))
            runtime = GenesisRuntime(settings)
            memory = MemoryService(settings.data_dir / "memory" / "genesis.db")
            runtime.register_service(
                ServiceDescriptor(
                    name="memory",
                    version="0.1.0",
                    description="Persistent project and conversation memory.",
                    service=memory,
                    dependencies=("kernel",),
                )
            )
            await runtime.start()
            memory.remember("neogen", "Milestone 011")
            self.assertIn("memory", runtime.snapshot().registry_entries)
            await runtime.stop()

    async def test_memory_rejects_invalid_roles_and_unstarted_access(self) -> None:
        service = MemoryService(Path("unused.db"))
        with self.assertRaises(RuntimeError):
            service.search("neogen", "anything")
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MemoryService(Path(temp_dir) / "memory.db")
            await service.start()
            with self.assertRaises(ValueError):
                service.add_turn("neogen", "main", "owner", "invalid")
            await service.stop()

    async def test_decision_memory_tracks_outcomes_revocation_and_owner_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MemoryService(Path(temp_dir) / "memory.db")
            await service.start()
            decision = service.record_decision(
                "owner:one", "Prefer reversible releases", context="NeoGen deployment", confidence=0.95
            )
            service.update_decision("owner:one", decision.id, outcome="Rollback completed cleanly")
            self.assertEqual(service.decisions("owner:one")[0].outcome, "Rollback completed cleanly")
            self.assertEqual(service.decisions("owner:two"), ())
            service.update_decision("owner:one", decision.id, revoke=True)
            self.assertEqual(service.decisions("owner:one"), ())
            self.assertEqual(service.decisions("owner:one", include_revoked=True)[0].status, "revoked")
            await service.stop()

    async def test_autonomy_adapts_to_risk_and_impact(self) -> None:
        self.assertEqual(MemoryService.assess_autonomy(0.1).mode, "observe")
        self.assertEqual(MemoryService.assess_autonomy(0.3).mode, "advise")
        prepared = MemoryService.assess_autonomy(0.5)
        self.assertEqual(prepared.mode, "prepare")
        self.assertTrue(prepared.approval_required)
        human = MemoryService.assess_autonomy(0.3, irreversible=True, sensitive=True)
        self.assertEqual(human.mode, "human_only")
        self.assertTrue(human.approval_required)

    async def test_memory_bounds_and_owner_scoped_forgetting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MemoryService(Path(temp_dir) / "memory.db")
            await service.start()
            service.remember("owner:one", "keep")
            service.add_turn("owner:one", "chat", "user", "private")
            service.record_decision("owner:one", "reversible releases")
            service.remember("owner:two", "untouched")
            with self.assertRaises(ValueError):
                service.remember("owner:one", "x" * (service.max_memory_length + 1))
            deleted = service.forget_project("owner:one")
            self.assertEqual(sum(deleted.values()), 3)
            self.assertEqual(service.search("owner:one", "keep"), ())
            self.assertEqual(service.search("owner:two", "untouched")[0].content, "untouched")
            await service.stop()


if __name__ == "__main__":
    unittest.main()
