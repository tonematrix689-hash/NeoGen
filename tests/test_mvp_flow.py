"""End-to-end regression tests for the NeoGen MVP critical path."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from genesis.services.kernel import NeoGenKernel


class NeoGenMvpFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.kernel = NeoGenKernel.build(
            enable_puter=False,
            storage_path=root / "neogen.db",
            workspace_path=root / "workspace",
        )

    def tearDown(self) -> None:
        self.kernel.close()
        self.temp.cleanup()

    def test_identity_avatar_wallet_marketplace_inventory_flow(self) -> None:
        seller = self.kernel.identity.register(
            email="seller@example.com",
            password="seller-password-123",
            display_name="Seller",
        )
        buyer = self.kernel.identity.register(
            email="buyer@example.com",
            password="buyer-password-123",
            display_name="Buyer",
        )

        seller_session = self.kernel.identity.authenticate(
            email=seller.email,
            password="seller-password-123",
        )
        self.assertEqual(self.kernel.identity.resolve(seller_session.token).id, seller.id)

        avatar = self.kernel.game.get_or_create_avatar(buyer.id)
        updated_avatar = self.kernel.game.update_avatar(
            buyer.id,
            name="Nova",
            appearance={"hair": "silver", "armor": "genesis"},
        )
        self.assertEqual(updated_avatar.id, avatar.id)
        self.assertEqual(updated_avatar.name, "Nova")
        self.assertEqual(updated_avatar.appearance["armor"], "genesis")

        self.kernel.game.ensure_wallet(seller.id, opening_balance=100)
        self.kernel.game.ensure_wallet(buyer.id, opening_balance=1000)
        listing = self.kernel.game.create_listing(
            seller.id,
            name="Genesis Blade",
            description="MVP marketplace item",
            price=250,
            item={"name": "Genesis Blade", "item_type": "weapon", "rarity": 12},
        )
        purchased = self.kernel.game.purchase(buyer.id, listing["id"])

        self.assertEqual(purchased["status"], "sold")
        self.assertEqual(purchased["buyer_id"], buyer.id)
        self.assertEqual(self.kernel.game.wallet(buyer.id)["balance"], 750)
        self.assertEqual(self.kernel.game.wallet(seller.id)["balance"], 350)

        inventory = self.kernel.game.inventory(buyer.id)
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]["name"], "Genesis Blade")
        self.assertEqual(inventory[0]["rarity"], 12)
        self.assertEqual(len(self.kernel.game.transactions(buyer.id)), 2)

    def test_workspace_and_terminal_flow(self) -> None:
        document = self.kernel.workspace.write(
            "project/hello.py",
            "print('neo genesis')\n",
        )
        self.assertEqual(document.path, "project/hello.py")
        self.assertEqual(self.kernel.workspace.read(document.path).content, "print('neo genesis')\n")

        entries = self.kernel.workspace.list("project")
        self.assertEqual([entry.name for entry in entries], ["hello.py"])

        result = self.kernel.terminal.execute(
            [sys.executable, "hello.py"],
            cwd="project",
            timeout_seconds=10,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("neo genesis", result.stdout)
        self.assertFalse(result.timed_out)

    def test_persistence_survives_kernel_restart(self) -> None:
        root = Path(self.temp.name)
        user = self.kernel.identity.register(
            email="persist@example.com",
            password="persistent-password-123",
            display_name="Persistent User",
        )
        self.kernel.game.update_avatar(user.id, name="Legacy", appearance={"core": "eternal"})
        self.kernel.workspace.write("legacy.txt", "persistent world")
        self.kernel.close()

        self.kernel = NeoGenKernel.build(
            enable_puter=False,
            storage_path=root / "neogen.db",
            workspace_path=root / "workspace",
        )
        restored = self.kernel.game.get_or_create_avatar(user.id)
        self.assertEqual(restored.name, "Legacy")
        self.assertEqual(restored.appearance["core"], "eternal")
        self.assertEqual(self.kernel.workspace.read("legacy.txt").content, "persistent world")


if __name__ == "__main__":
    unittest.main()
