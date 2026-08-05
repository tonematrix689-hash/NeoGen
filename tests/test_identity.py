"""Identity and designated-owner regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from genesis.services.events import EventBus
from genesis.services.identity import DEFAULT_OWNER_EMAIL, IdentityService
from genesis.services.storage import SQLiteStore


class IdentityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.temp.name) / "identity.db")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_designated_email_is_owner_even_when_not_first_account(self) -> None:
        identity = IdentityService(self.store, EventBus())
        first = identity.register(
            email="first@example.com",
            password="first-password-123",
            display_name="First User",
        )
        owner = identity.register(
            email=DEFAULT_OWNER_EMAIL,
            password="owner-password-123",
            display_name="NeoGen Owner",
        )

        self.assertIn("owner", first.roles)
        self.assertEqual(owner.email, DEFAULT_OWNER_EMAIL)
        self.assertTrue({"user", "admin", "owner"}.issubset(owner.roles))

    def test_existing_designated_account_is_promoted_on_restart(self) -> None:
        initial = IdentityService(
            self.store,
            EventBus(),
            owner_email="someone-else@example.com",
        )
        initial.register(
            email="first@example.com",
            password="first-password-123",
            display_name="First User",
        )
        account = initial.register(
            email=DEFAULT_OWNER_EMAIL,
            password="owner-password-123",
            display_name="NeoGen Owner",
        )
        self.assertNotIn("owner", account.roles)

        reconciled = IdentityService(self.store, EventBus())
        promoted = reconciled.get_user(account.id)

        self.assertTrue({"user", "admin", "owner"}.issubset(promoted.roles))
        session = reconciled.authenticate(
            email=DEFAULT_OWNER_EMAIL,
            password="owner-password-123",
        )
        self.assertEqual(session.user_id, account.id)


if __name__ == "__main__":
    unittest.main()
