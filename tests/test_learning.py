from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.app.learning import LearningService


class LearningServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_outcomes_persist_and_remain_project_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "learning.db"
            first = LearningService(database)
            await first.start()
            first.record_outcome("neogen", "coding", "careful", 1.0)
            first.record_outcome("other", "coding", "careful", 0.0)
            await first.stop()

            second = LearningService(database)
            await second.start()
            records = second.outcomes("neogen", "coding")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].reward, 1.0)
            await second.stop()

    async def test_ranking_explores_unseen_then_uses_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            learning = LearningService(Path(temp_dir) / "learning.db", exploration=0.0)
            await learning.start()
            learning.record_outcome("neogen", "coding", "alpha", 1.0)
            learning.record_outcome("neogen", "coding", "beta", 0.0)

            ranked = learning.rank_strategies("neogen", "coding", ("alpha", "beta", "new"))
            self.assertEqual(ranked[0].strategy, "new")
            ranked_seen = learning.rank_strategies("neogen", "coding", ("alpha", "beta"))
            self.assertEqual(ranked_seen[0].strategy, "alpha")
            await learning.stop()

    async def test_invalid_or_sensitive_free_form_outcomes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            learning = LearningService(Path(temp_dir) / "learning.db")
            await learning.start()
            with self.assertRaises(ValueError):
                learning.record_outcome("neogen", "coding", "strategy", 1.5)
            with self.assertRaises(ValueError):
                learning.record_outcome("neogen", "coding", "strategy", 1.0, source="web")
            await learning.stop()


if __name__ == "__main__":
    unittest.main()
