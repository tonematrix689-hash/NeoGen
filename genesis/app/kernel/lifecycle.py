"""Lifecycle orchestration for Genesis services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import inspect
import logging
from typing import Protocol


class LifecycleService(Protocol):
    """Protocol implemented by services managed by the kernel lifecycle."""

    async def start(self) -> None:
        """Start the service."""

    async def stop(self) -> None:
        """Stop the service."""


class LifecycleState(StrEnum):
    """Lifecycle states tracked for diagnostics."""

    REGISTERED = "registered"
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LifecycleRegistration:
    """A service and its lifecycle priority."""

    name: str
    service: LifecycleService
    priority: int = 100
    dependencies: tuple[str, ...] = ()


class LifecycleError(RuntimeError):
    """Raised when lifecycle orchestration fails."""


class LifecycleManager:
    """Starts services in priority order and stops them in reverse order."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("genesis.kernel.lifecycle")
        self._registrations: list[LifecycleRegistration] = []
        self._started: list[LifecycleRegistration] = []
        self._states: dict[str, LifecycleState] = {}

    def register(
        self,
        name: str,
        service: LifecycleService,
        *,
        priority: int = 100,
        dependencies: tuple[str, ...] = (),
    ) -> None:
        """Register a lifecycle-managed service."""

        if name in self._states:
            raise LifecycleError(f"Lifecycle service is already registered: {name}")
        self._registrations.append(LifecycleRegistration(name, service, priority, dependencies))
        self._registrations = self._ordered_registrations()
        self._states[name] = LifecycleState.REGISTERED

    async def start_all(self) -> None:
        """Start all registered services."""

        for registration in self._registrations:
            self._logger.info("Starting service %s", registration.name)
            try:
                await self._call(registration.service.start)
            except Exception as exc:
                self._states[registration.name] = LifecycleState.FAILED
                await self.stop_all()
                raise LifecycleError(f"Failed to start service {registration.name!r}") from exc
            else:
                self._started.append(registration)
                self._states[registration.name] = LifecycleState.STARTED

    async def stop_all(self) -> None:
        """Stop started services in reverse startup order."""

        while self._started:
            registration = self._started.pop()
            self._logger.info("Stopping service %s", registration.name)
            try:
                await self._call(registration.service.stop)
            except Exception:
                self._states[registration.name] = LifecycleState.FAILED
                self._logger.exception("Failed to stop service %s", registration.name)
            else:
                self._states[registration.name] = LifecycleState.STOPPED

    async def _call(self, method: object) -> None:
        result = method()
        if inspect.isawaitable(result):
            await result

    def _ordered_registrations(self) -> list[LifecycleRegistration]:
        registrations = {registration.name: registration for registration in self._registrations}
        ordered: list[LifecycleRegistration] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise LifecycleError(f"Lifecycle dependency cycle detected at {name!r}")
            registration = registrations.get(name)
            if registration is None:
                raise LifecycleError(f"Lifecycle dependency is not registered: {name}")
            visiting.add(name)
            for dependency in registration.dependencies:
                if dependency in registrations:
                    visit(dependency)
            visiting.remove(name)
            visited.add(name)
            ordered.append(registration)

        for registration in sorted(self._registrations, key=lambda item: (item.priority, item.name)):
            visit(registration.name)
        return ordered

    def state(self, name: str) -> LifecycleState | None:
        """Return one service lifecycle state."""

        return self._states.get(name)

    def states(self) -> dict[str, LifecycleState]:
        """Return a copy of lifecycle states for diagnostics."""

        return dict(self._states)
