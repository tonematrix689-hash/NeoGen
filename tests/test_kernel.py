from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from genesis.app.kernel.dependency_container import DependencyContainer, ServiceLifetime
from genesis.app.kernel.event_bus import Event, EventBus
from genesis.app.kernel.health import HealthStatus
from genesis.app.kernel.runtime import GenesisRuntime
from genesis.app.kernel.settings import GenesisSettings


class KernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_start_stop_and_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = GenesisRuntime(
                GenesisSettings(data_dir=Path(temp_dir), startup_timeout_seconds=2, shutdown_timeout_seconds=2)
            )
            await runtime.start()
            self.assertTrue(runtime.started)
            self.assertEqual(await runtime.health.overall_status(), HealthStatus.HEALTHY)
            self.assertTrue(runtime.container.contains("event_bus"))
            await runtime.stop()
            self.assertFalse(runtime.started)

    async def test_event_bus_invokes_async_and_sync_handlers(self) -> None:
        event_bus = EventBus(history_limit=10)
        seen: list[str] = []

        def sync_handler(event: Event) -> None:
            seen.append(f"sync:{event.name}")

        async def async_handler(event: Event) -> None:
            await asyncio.sleep(0)
            seen.append(f"async:{event.name}")

        event_bus.subscribe("kernel.test", sync_handler)
        event_bus.subscribe("kernel.test", async_handler)
        await event_bus.publish(Event("kernel.test"))

        self.assertEqual(set(seen), {"sync:kernel.test", "async:kernel.test"})
        self.assertEqual(event_bus.history()[-1].name, "kernel.test")

    async def test_dependency_container_lifetimes(self) -> None:
        container = DependencyContainer()
        container.register_factory("singleton", lambda _: object())
        container.register_factory("transient", lambda _: object(), lifetime=ServiceLifetime.TRANSIENT)

        self.assertIs(container.resolve("singleton"), container.resolve("singleton"))
        self.assertIsNot(container.resolve("transient"), container.resolve("transient"))


if __name__ == "__main__":
    unittest.main()
