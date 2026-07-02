"""Lifecycle orchestration for Genesis services."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import logging
from typing import Protocol


class LifecycleService(Protocol):
    """Protocol implemented by services managed by the kernel lifecycle."""

    async def start(self) -> None:
        """Start the service."""

    async def stop(self) -> None:
        """Stop the service."""


@dataclass(frozen=True, slots=True)
class LifecycleRegistration:
    """A service and its lifecycle priority."""

    name: str
    service: LifecycleService
    priority: int = 100


class LifecycleManager:
    """Starts services in priority order and stops them in reverse order."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("genesis.kernel.lifecycle")
        self._registrations: list[LifecycleRegistration] = []
        self._started: list[LifecycleRegistration] = []

    def register(self, name: str, service: LifecycleService, *, priority: int = 100) -> None:
        """Register a lifecycle-managed service."""

        self._registrations.append(LifecycleRegistration(name, service, priority))
        self._registrations.sort(key=lambda registration: registration.priority)

    async def start_all(self) -> None:
        """Start all registered services."""

        for registration in self._registrations:
            self._logger.info("Starting service %s", registration.name)
            await self._call(registration.service.start)
            self._started.append(registration)

    async def stop_all(self) -> None:
        """Stop started services in reverse startup order."""

        while self._started:
            registration = self._started.pop()
            self._logger.info("Stopping service %s", registration.name)
            try:
                await self._call(registration.service.stop)
            except Exception:
                self._logger.exception("Failed to stop service %s", registration.name)

    async def _call(self, method: object) -> None:
        result = method()
        if inspect.isawaitable(result):
            await result
