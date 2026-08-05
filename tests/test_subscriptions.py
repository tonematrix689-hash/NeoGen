"""Subscription catalogue and entitlement tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.services.events import EventBus
from genesis.services.storage import SQLiteStore
from genesis.services.subscriptions import SubscriptionError, SubscriptionService


class SubscriptionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.temp.name) / "subscriptions.db")
        self.service = SubscriptionService(self.store, EventBus())

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_catalog_has_ten_levels_plus_business_and_enterprise(self) -> None:
        plans = self.service.catalog()
        self.assertEqual(len(plans), 14)
        self.assertEqual([plan.level for plan in plans[:10]], list(range(1, 11)))
        self.assertEqual([plan.id for plan in plans[10:]], ["admin", "owner", "business", "enterprise"])
        self.assertEqual(self.service.plan("admin").level, 11)
        self.assertEqual(self.service.plan("owner").level, 12)
        self.assertIn("compliance_controls", self.service.plan("owner").abilities)

    def test_higher_levels_accumulate_abilities(self) -> None:
        level_one = set(self.service.plan("level-1").abilities)
        level_ten = set(self.service.plan("level-10").abilities)
        self.assertLess(len(level_one), len(level_ten))
        self.assertTrue(level_one.issubset(level_ten))
        self.assertIn("agent_council", level_ten)
        self.assertIn("afterlife_forge", level_ten)

    def test_paid_request_does_not_grant_entitlements_before_activation(self) -> None:
        current = self.service.ensure("user:one")
        self.assertEqual(current.plan_id, "level-1")
        requested = self.service.request("user:one", "level-9")
        self.assertTrue(requested["checkout_required"])
        self.assertEqual(requested["subscription"].state, "pending_provider")
        self.assertFalse(self.service.has_ability("user:one", "agent_council"))

        active = self.service.activate("user:one", "level-9", provider="test-provider")
        self.assertEqual(active.state, "active")
        self.assertTrue(self.service.has_ability("user:one", "agent_council"))

    def test_unknown_plan_is_rejected(self) -> None:
        with self.assertRaises(SubscriptionError):
            self.service.request("user:one", "level-99")

    def test_privileged_levels_are_visible_but_not_self_requestable(self) -> None:
        with self.assertRaises(SubscriptionError):
            self.service.request("user:one", "admin")
        with self.assertRaises(SubscriptionError):
            self.service.request("user:one", "owner")


if __name__ == "__main__":
    unittest.main()
