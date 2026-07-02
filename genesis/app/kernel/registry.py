"""Service discovery registry for Genesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from threading import RLock


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """Metadata describing a registered service or capability."""

    name: str
    version: str
    kind: str
    description: str
    dependencies: tuple[str, ...] = ()
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ServiceRegistry:
    """Runtime registry for kernel services and future capabilities."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("genesis.kernel.registry")
        self._entries: dict[str, RegistryEntry] = {}
        self._lock = RLock()

    def register(self, entry: RegistryEntry) -> None:
        """Register or replace a service entry."""

        with self._lock:
            self._entries[entry.name] = entry
            self._logger.info("Registered %s %s", entry.kind, entry.name)

    def get(self, name: str) -> RegistryEntry | None:
        """Return a registry entry by name."""

        with self._lock:
            return self._entries.get(name)

    def require(self, name: str) -> RegistryEntry:
        """Return a registry entry or raise when absent."""

        entry = self.get(name)
        if entry is None:
            raise KeyError(f"Registry entry is not available: {name}")
        return entry

    def list(self, *, kind: str | None = None) -> tuple[RegistryEntry, ...]:
        """List registered entries, optionally filtered by kind."""

        with self._lock:
            entries = tuple(self._entries.values())
        if kind is None:
            return tuple(sorted(entries, key=lambda entry: entry.name))
        return tuple(sorted((entry for entry in entries if entry.kind == kind), key=lambda entry: entry.name))
