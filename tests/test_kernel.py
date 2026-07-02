from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from genesis.app.kernel.dependency_container import DependencyContainer, ServiceLifetime
from genesis.app.kernel.event_bus import Event, EventBus
from genesis.app.kernel.health import HealthStatus
from genesis.app.kernel.runtime import GenesisRuntime, RuntimeState, ServiceDescriptor
from genesis.app.kernel.settings import GenesisSettings


class RecordingService:
    def __init__(self, events: list[str], name: str, *, fail_start: bool = False) -> None:
        self._events = events
        self._name = name
        self._fail_start = fail_start

    async def start(self) -> None:
        self._events.append(f"start:{self._name}")
        if self._fail_start:
            raise RuntimeError(f"{self._name} failed")

    async def stop(self) -> None:
        self._events.append(f"stop:{self._name}")


class KernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_start_stop_and_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = GenesisRuntime(
                GenesisSettings(data_dir=Path(temp_dir), startup_timeout_seconds=2, shutdown_timeout_seconds=2)
            )
            await runtime.start()
            self.assertTrue(runtime.started)
            self.assertEqual(runtime.state, RuntimeState.RUNNING)
            self.assertEqual(await runtime.health.overall_status(), HealthStatus.HEALTHY)
            self.assertTrue(runtime.container.contains("event_bus"))
            self.assertEqual(runtime.snapshot().state, RuntimeState.RUNNING)
            await runtime.stop()
            self.assertFalse(runtime.started)
            self.assertEqual(runtime.state, RuntimeState.STOPPED)

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

    async def test_runtime_registers_services_in_lifecycle_order(self) -> None:
        events: list[str] = []
        runtime = GenesisRuntime(GenesisSettings(startup_timeout_seconds=2, shutdown_timeout_seconds=2))

        runtime.register_service(
            ServiceDescriptor(
                name="service.low",
                version="1.0.0",
                description="Low priority service.",
                service=RecordingService(events, "low"),
                priority=20,
            )
        )
        runtime.register_service(
            ServiceDescriptor(
                name="service.high",
                version="1.0.0",
                description="High priority service.",
                service=RecordingService(events, "high"),
                priority=10,
                dependencies=("service.low",),
            )
        )

        await runtime.start()
        await runtime.stop()

        self.assertEqual(events, ["start:low", "start:high", "stop:high", "stop:low"])
        self.assertIn("service.high", runtime.snapshot().registry_entries)

    async def test_runtime_rolls_back_started_services_when_start_fails(self) -> None:
        events: list[str] = []
        runtime = GenesisRuntime(GenesisSettings(startup_timeout_seconds=2, shutdown_timeout_seconds=2))
        runtime.register_service(
            ServiceDescriptor(
                name="service.ready",
                version="1.0.0",
                description="Service that starts.",
                service=RecordingService(events, "ready"),
                priority=10,
            )
        )
        runtime.register_service(
            ServiceDescriptor(
                name="service.fail",
                version="1.0.0",
                description="Service that fails.",
                service=RecordingService(events, "fail", fail_start=True),
                priority=20,
            )
        )

        with self.assertRaises(Exception):
            await runtime.start()

        self.assertEqual(runtime.state, RuntimeState.FAILED)
        self.assertEqual(events, ["start:ready", "start:fail", "stop:ready"])


if __name__ == "__main__":
    unittest.main()
