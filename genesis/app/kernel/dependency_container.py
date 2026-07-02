"""Dependency injection container for Genesis services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import logging
from threading import RLock
from typing import Any, TypeVar


T = TypeVar("T")
Factory = Callable[["DependencyContainer"], Any]


class ServiceLifetime(StrEnum):
    """Supported dependency lifetimes."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"
    INSTANCE = "instance"


@dataclass(slots=True)
class _Registration:
    key: str
    factory: Factory | None
    lifetime: ServiceLifetime
    instance: Any = None


class DependencyResolutionError(RuntimeError):
    """Raised when a dependency cannot be resolved."""


class DependencyContainer:
    """Small dependency injection container used by the Genesis kernel."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("genesis.kernel.container")
        self._registrations: dict[str, _Registration] = {}
        self._lock = RLock()

    def register_instance(self, key: str, instance: Any) -> None:
        """Register an already constructed service instance."""

        with self._lock:
            self._registrations[key] = _Registration(key, None, ServiceLifetime.INSTANCE, instance)
            self._logger.debug("Registered dependency instance %s", key)

    def register_factory(
        self,
        key: str,
        factory: Factory,
        *,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> None:
        """Register a service factory."""

        if lifetime is ServiceLifetime.INSTANCE:
            raise ValueError("Use register_instance for instance lifetime dependencies.")
        with self._lock:
            self._registrations[key] = _Registration(key, factory, lifetime)
            self._logger.debug("Registered dependency factory %s", key)

    def resolve(self, key: str, expected_type: type[T] | None = None) -> T:
        """Resolve a dependency by key and optionally validate its type."""

        with self._lock:
            registration = self._registrations.get(key)
            if registration is None:
                raise DependencyResolutionError(f"Dependency is not registered: {key}")
            instance = self._build(registration)
        if expected_type is not None and not isinstance(instance, expected_type):
            raise DependencyResolutionError(
                f"Dependency {key!r} resolved to {type(instance).__name__}, expected {expected_type.__name__}."
            )
        return instance

    def _build(self, registration: _Registration) -> Any:
        if registration.lifetime is ServiceLifetime.TRANSIENT:
            if registration.factory is None:
                raise DependencyResolutionError(f"Dependency {registration.key!r} has no factory.")
            return registration.factory(self)
        if registration.instance is None:
            if registration.factory is None:
                raise DependencyResolutionError(f"Dependency {registration.key!r} has no instance.")
            registration.instance = registration.factory(self)
        return registration.instance

    def contains(self, key: str) -> bool:
        """Return whether a dependency key is registered."""

        with self._lock:
            return key in self._registrations

    def keys(self) -> tuple[str, ...]:
        """Return registered dependency keys."""

        with self._lock:
            return tuple(sorted(self._registrations))
