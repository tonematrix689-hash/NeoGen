from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.services.events import EventBus
from genesis.services.game import GameError, GameService
from genesis.services.storage import SQLiteStore


class DeadCoinForgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.temp.name) / "forge.db")
        self.game = GameService(self.store, EventBus())
        self.game.ensure_wallet("user:one", opening_balance=10_000)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_development_coin_terms_are_explicit_and_not_executable(self) -> None:
        quote = self.game.quote_coins(1_000)
        self.assertEqual(quote["coins"], 1_000)
        self.assertEqual(quote["currency"], "COTD")
        self.assertFalse(quote["executable"])
        self.assertFalse(quote["terms"]["cash_redemption_enabled"])
        self.assertEqual(self.game.wallet("user:one")["currency"], "COTD")

    def test_prompt_forge_builds_layers_and_deducts_ledgered_cost(self) -> None:
        avatar = self.game.create_forge_avatar(
            "user:one",
            name="Many-Eyed Herald",
            prompt="An octopus-headed guardian with hooves, a tail and six arms",
        )
        before = self.game.wallet("user:one")["balance"]
        forged = self.game.add_forge_layer(
            "user:one",
            avatar["id"],
            layer_type="bones",
            design_prompt="A flexible titanium endoskeleton supporting six arms",
            abilities=("pressure resistance", "multi-limb coordination"),
        )
        cost = self.game.layer_cost(1, "bones")
        self.assertEqual(self.game.wallet("user:one")["balance"], before - cost)
        self.assertEqual(forged["layers"]["bones"]["cost"], cost)
        self.assertEqual(self.game.transactions("user:one")[-1]["reason"], "forge_layer")

    def test_rarity_progresses_to_1000_with_increasing_cost_and_power_thresholds(self) -> None:
        avatar = self.game.create_forge_avatar("user:one", name="Nova", prompt="Living starlight")
        self.assertGreater(self.game.rarity_upgrade_cost(500), self.game.rarity_upgrade_cost(1))
        record = self.store.get(self.game.forge_ns, avatar["id"])
        advanced = dict(record.value)
        advanced["rarity_level"] = 9
        self.store.put(self.game.forge_ns, avatar["id"], advanced, expected_version=record.version)
        upgraded = self.game.upgrade_forge_avatar("user:one", avatar["id"])
        self.assertEqual(upgraded["rarity_level"], 10)
        self.assertEqual(upgraded["powers"][0]["status"], "awaiting_ai_design")
        with self.assertRaises(GameError):
            self.game.rarity_upgrade_cost(1_000)

    def test_forge_assets_are_owner_scoped(self) -> None:
        avatar = self.game.create_forge_avatar("user:one", name="Private", prompt="Owner only")
        with self.assertRaisesRegex(GameError, "access denied"):
            self.game.forge_avatar("user:two", avatar["id"])


if __name__ == "__main__":
    unittest.main()
