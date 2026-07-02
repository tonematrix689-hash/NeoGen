"""Health reporting for Genesis kernel services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import inspect
import logging
from typing import Any


HealthCheck = Callable[[], "HealthReport | Awaitable[HealthReport]"]


class HealthStatus(StrEnum):
    """Health states understood by the kernel."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Health result returned by a service or capability."""

    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class HealthMonitor:
    """Coordinates health checks for kernel services and future capabilities."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("genesis.kernel.health")
        self._checks: dict[str, HealthCheck] = {}

    def register(self, name: str, check: HealthCheck) -> None:
        """Register a health check by name."""

        self._checks[name] = check

    async def check(self, name: str) -> HealthReport:
        """Run one health check."""

        check = self._checks.get(name)
        if check is None:
            return HealthReport(name, HealthStatus.UNHEALTHY, "Health check is not registered.")
        try:
            result = check()
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as exc:
            self._logger.exception("Health check failed for %s", name)
            return HealthReport(name, HealthStatus.UNHEALTHY, str(exc))

    async def check_all(self) -> tuple[HealthReport, ...]:
        """Run every registered health check."""

        reports = [await self.check(name) for name in sorted(self._checks)]
        return tuple(reports)

    async def overall_status(self) -> HealthStatus:
        """Return the aggregate health status."""

        reports = await self.check_all()
        if any(report.status is HealthStatus.UNHEALTHY for report in reports):
            return HealthStatus.UNHEALTHY
        if any(report.status is HealthStatus.DEGRADED for report in reports):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY
