"""Genesis kernel public API."""

from genesis.app.kernel.dependency_container import DependencyContainer, ServiceLifetime
from genesis.app.kernel.event_bus import Event, EventBus
from genesis.app.kernel.health import HealthMonitor, HealthReport, HealthStatus
from genesis.app.kernel.registry import RegistryEntry, ServiceRegistry
from genesis.app.kernel.runtime import GenesisRuntime, RuntimeState, ServiceDescriptor
from genesis.app.kernel.settings import GenesisSettings
from genesis.app.kernel.version import __version__

__all__ = [
    "DependencyContainer",
    "Event",
    "EventBus",
    "GenesisRuntime",
    "GenesisSettings",
    "HealthMonitor",
    "HealthReport",
    "HealthStatus",
    "RegistryEntry",
    "RuntimeState",
    "ServiceLifetime",
    "ServiceDescriptor",
    "ServiceRegistry",
    "__version__",
]
