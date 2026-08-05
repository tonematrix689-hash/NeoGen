"""Legal notice versioning, readiness, and acceptance tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from genesis.services.events import EventBus
from genesis.services.legal import DOCUMENT_VERSION, LegalError, LegalService, OPERATOR_ENVIRONMENT
from genesis.services.storage import SQLiteStore


class LegalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.temp.name) / "legal.db")
        self.service = LegalService(self.store, EventBus())

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_catalog_exposes_versioned_mandatory_notices(self) -> None:
        documents = self.service.catalog()
        self.assertGreaterEqual(len(documents), 10)
        self.assertEqual({d.id for d in documents if d.mandatory}, {"terms", "privacy", "acceptable-use", "ai-transparency"})
        self.assertTrue(all(document.version == DOCUMENT_VERSION for document in documents))

    def test_acceptance_is_bound_to_every_current_version(self) -> None:
        required = {document.id: document.version for document in self.service.catalog() if document.mandatory}
        accepted = self.service.accept("user:one", required, age_confirmed=True, locale="en-AU")
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["record"]["documents"], required)

    def test_stale_or_incomplete_acceptance_is_rejected(self) -> None:
        with self.assertRaises(LegalError):
            self.service.accept("user:one", {"terms": DOCUMENT_VERSION}, age_confirmed=True)
        required = {document.id: document.version for document in self.service.catalog() if document.mandatory}
        with self.assertRaises(LegalError):
            self.service.accept("user:one", required, age_confirmed=False)

    def test_public_commerce_readiness_requires_operator_configuration(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.service.public_configuration()["ready_for_public_commerce"])
        values = {variable: "configured" for variable in OPERATOR_ENVIRONMENT.values()}
        with patch.dict(os.environ, values, clear=True):
            self.assertTrue(self.service.public_configuration()["ready_for_public_commerce"])


if __name__ == "__main__":
    unittest.main()
