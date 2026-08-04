"""Restart and recovery coverage for NeoGen durable storage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.services.kernel import NeoGenKernel
from genesis.services.storage import SQLiteStore, StorageError


class StorageRecoveryTests(unittest.TestCase):
    def test_store_persists_records_across_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "neogen.db"
            first = SQLiteStore(path)
            stored = first.put(
                "project.state",
                "neogen",
                {"status": "building", "version": 1},
            )
            self.assertEqual(stored.version, 1)
            first.close()

            second = SQLiteStore(path)
            recovered = second.get("project.state", "neogen")
            self.assertEqual(recovered.value["status"], "building")
            self.assertEqual(recovered.version, 1)
            second.close()

    def test_optimistic_version_conflicts_are_rejected(self) -> None:
        store = SQLiteStore()
        initial = store.put("settings", "routing", {"mode": "balanced"})
        updated = store.put(
            "settings",
            "routing",
            {"mode": "quality"},
            expected_version=initial.version,
        )
        self.assertEqual(updated.version, 2)
        with self.assertRaises(StorageError):
            store.put(
                "settings",
                "routing",
                {"mode": "fast"},
                expected_version=initial.version,
            )
        store.close()

    def test_kernel_checkpoint_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.db"
            first = NeoGenKernel.build(storage_path=path)
            checkpoint_id = first.checkpoint(
                category="mission",
                subject_id="mission:neogen-1",
                state={
                    "goal": "Complete durable NeoGen runtime",
                    "status": "executing",
                    "completed_steps": ["storage", "checkpoint-manager"],
                },
            )
            self.assertEqual(first.health()["checkpoints"]["total"], 1)
            first.close()

            second = NeoGenKernel.build(storage_path=path)
            recovered = second.checkpoints.load(checkpoint_id)
            self.assertEqual(recovered.category, "mission")
            self.assertEqual(recovered.subject_id, "mission:neogen-1")
            self.assertEqual(recovered.state["status"], "executing")
            self.assertEqual(
                recovered.state["completed_steps"],
                ["storage", "checkpoint-manager"],
            )
            self.assertEqual(second.health()["storage"]["records"], 1)
            second.close()

    def test_checkpoint_sequence_increments_for_same_identifier(self) -> None:
        kernel = NeoGenKernel.build()
        first = kernel.checkpoints.save(
            category="workflow",
            subject_id="workflow:release",
            checkpoint_id="checkpoint:release",
            state={"step": 1},
        )
        second = kernel.checkpoints.save(
            category="workflow",
            subject_id="workflow:release",
            checkpoint_id="checkpoint:release",
            state={"step": 2},
        )
        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(kernel.checkpoints.load("checkpoint:release").state["step"], 2)
        kernel.close()

    def test_snapshot_restore_copies_all_namespaces(self) -> None:
        source = SQLiteStore()
        source.put("memory", "one", {"content": "NeoGen"})
        source.put("plans", "two", {"status": "ready"})
        snapshot = source.snapshot()

        target = SQLiteStore()
        restored = target.restore(snapshot, replace=True)
        self.assertEqual(restored, 2)
        self.assertEqual(target.namespaces(), ("memory", "plans"))
        self.assertEqual(target.get("plans", "two").value["status"], "ready")
        source.close()
        target.close()


if __name__ == "__main__":
    unittest.main()
