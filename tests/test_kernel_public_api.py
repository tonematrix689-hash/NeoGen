"""Regression tests for the Genesis kernel public API."""

from __future__ import annotations

import unittest

from genesis.app.kernel import GenesisRuntime, RuntimeState, ServiceDescriptor


class KernelPublicApiTests(unittest.TestCase):
    def test_public_runtime_contracts_import(self) -> None:
        self.assertEqual(RuntimeState.INITIALIZED, "initialized")
        self.assertEqual(ServiceDescriptor("test", "object").name, "test")

    def test_runtime_exposes_state_and_service_descriptors(self) -> None:
        runtime = GenesisRuntime()

        self.assertEqual(runtime.state, RuntimeState.INITIALIZED)
        self.assertFalse(runtime.started)

        descriptors = {descriptor.name: descriptor for descriptor in runtime.describe_services()}
        self.assertIn("settings", descriptors)
        self.assertIn("event_bus", descriptors)
        self.assertIn("health", descriptors)
        self.assertTrue(all(descriptor.registered for descriptor in descriptors.values()))

        snapshot = runtime.snapshot()
        self.assertEqual(snapshot.state, RuntimeState.INITIALIZED)
        self.assertFalse(snapshot.started)


if __name__ == "__main__":
    unittest.main()
