"""Genesis kernel runtime.

The runtime is the first concrete object created by Genesis. It owns kernel-level concerns only:
configuration, logging, events, dependency injection, service discovery, lifecycle, and health.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
import logging
from types import TracebackType

from genesis.app.kernel.config import ConfigProvider
from genesis.app.kernel.dependency_container import DependencyContainer
from genesis.app.kernel.event_bus import Event, EventBus
from genesis.app.kernel.health import HealthMonitor, HealthReport, HealthStatus
from genesis.app.kernel.lifecycle import LifecycleManager
from genesis.app.kernel.logger import configure_logging
from genesis.app.kernel.registry import RegistryEntry, ServiceRegistry
from genesis.app.kernel.settings import GenesisSettings
from genesis.app.kernel.version import __version__


class RuntimeState(StrEnum):
    """Runtime states exposed for diagnostics and orchestration."""

    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class RuntimeStateError(RuntimeError):
    """Raised when the runtime is used in an invalid state."""


@dataclass(frozen=True, slots=True)
class ServiceDescriptor:
    """Description of a service registered with the Genesis runtime."""

    name: str
    version: str
    description: str
    service: object
    kind: str = "service"
    priority: int = 100
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Diagnostics snapshot for runtime status."""

    app_name: str
    version: str
    environment: str
    started: bool
    state: RuntimeState
    services: tuple[str, ...]
    registry_entries: tuple[str, ...]


class GenesisRuntime:
    """Genesis kernel runtime and composition root."""

    def __init__(self, settings: GenesisSettings | None = None) -> None:
        self.settings = settings or GenesisSettings.from_env()
        self.logger = configure_logging(self.settings.log_level)
        self.config = ConfigProvider(self.settings)
        self.container = DependencyContainer(logger=logging.getLogger("genesis.kernel.container"))
        self.event_bus = EventBus(
            history_limit=self.settings.event_history_limit,
            logger=logging.getLogger("genesis.kernel.event_bus"),
        )
        self.registry = ServiceRegistry(logger=logging.getLogger("genesis.kernel.registry"))
        self.lifecycle = LifecycleManager(logger=logging.getLogger("genesis.kernel.lifecycle"))
        self.health = HealthMonitor(logger=logging.getLogger("genesis.kernel.health"))
        self._started = False
        self._state = RuntimeState.INITIALIZED
        self._register_kernel_services()

    @property
    def started(self) -> bool:
        """Return whether the runtime has completed startup."""

        return self._started

    @property
    def state(self) -> RuntimeState:
        """Return the current runtime state."""

        return self._state

    def register_service(self, descriptor: ServiceDescriptor) -> None:
        """Register a service with discovery, lifecycle, and health systems."""

        if self._started:
            raise RuntimeStateError("Cannot register services after runtime startup has begun.")
        self.container.register_instance(descriptor.name, descriptor.service)
        self.registry.register(
            RegistryEntry(
                name=descriptor.name,
                version=descriptor.version,
                kind=descriptor.kind,
                description=descriptor.description,
                dependencies=descriptor.dependencies,
            )
        )
        self.lifecycle.register(
            descriptor.name,
            descriptor.service,
            priority=descriptor.priority,
            dependencies=descriptor.dependencies,
        )

    async def start(self) -> None:
        """Start the Genesis kernel."""

        if self._started:
            raise RuntimeStateError("Genesis runtime is already started.")
        self._state = RuntimeState.STARTING
        self.settings.ensure_directories()
        self.logger.info("Starting Genesis kernel %s", __version__)
        try:
            await asyncio.wait_for(self.lifecycle.start_all(), timeout=self.settings.startup_timeout_seconds)
        except Exception:
            self._state = RuntimeState.FAILED
            self.logger.exception("Genesis kernel failed to start")
            raise
        self._started = True
        self._state = RuntimeState.RUNNING
        await self.event_bus.publish(Event("kernel.started", {"version": __version__}))

    async def stop(self) -> None:
        """Stop the Genesis kernel."""

        if not self._started:
            return
        self._state = RuntimeState.STOPPING
        self.logger.info("Stopping Genesis kernel")
        await self.event_bus.publish(Event("kernel.stopping", {"version": __version__}))
        await asyncio.wait_for(self.lifecycle.stop_all(), timeout=self.settings.shutdown_timeout_seconds)
        self._started = False
        self._state = RuntimeState.STOPPED
        await self.event_bus.publish(Event("kernel.stopped", {"version": __version__}))
        await self.event_bus.close()

    async def __aenter__(self) -> "GenesisRuntime":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()

    def snapshot(self) -> RuntimeSnapshot:
        """Return runtime diagnostics."""

        return RuntimeSnapshot(
            app_name=self.settings.app_name,
            version=__version__,
            environment=self.settings.environment,
            started=self._started,
            state=self._state,
            services=self.container.keys(),
            registry_entries=tuple(entry.name for entry in self.registry.list()),
        )

    def _register_kernel_services(self) -> None:
        self.container.register_instance("settings", self.settings)
        self.container.register_instance("config", self.config)
        self.container.register_instance("logger", self.logger)
        self.container.register_instance("event_bus", self.event_bus)
        self.container.register_instance("registry", self.registry)
        self.container.register_instance("lifecycle", self.lifecycle)
        self.container.register_instance("health", self.health)

        self.registry.register(
            RegistryEntry(
                name="kernel",
                version=__version__,
                kind="kernel",
                description="Genesis kernel runtime services.",
            )
        )
        self.health.register(
            "kernel",
            lambda: HealthReport(
                name="kernel",
                status=HealthStatus.HEALTHY if self._started else HealthStatus.DEGRADED,
                message="Kernel is running." if self._started else "Kernel is initialized but not started.",
                details={"version": __version__, "environment": self.settings.environment},
            ),
        )
