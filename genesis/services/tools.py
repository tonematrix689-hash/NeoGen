"""Governed tool registration, execution, health, and audit results for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from time import perf_counter
from typing import Any, Callable, Iterable

from .events import EventBus, EventSeverity
from .permissions import PermissionManager, PermissionScope


class ToolError(RuntimeError):
    """Base error for tool operations."""


class ToolHealth(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    id: str
    name: str
    description: str
    capabilities: frozenset[str]
    required_permissions: frozenset[PermissionScope]
    timeout_seconds: float
    cost_score: float
    platforms: frozenset[str]
    health: ToolHealth = ToolHealth.UNKNOWN
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ToolRequest:
    subject_id: str
    tool_id: str
    operation: str
    arguments: dict[str, Any]
    resource: str = "*"
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_id: str
    operation: str
    success: bool
    output: Any
    duration_ms: float
    error: str | None
    executed_at: datetime


ToolHandler = Callable[[ToolRequest], Any]
HealthCheck = Callable[[], ToolHealth]


class ToolRegistry:
    """Permission-aware tool catalog and execution boundary."""

    def __init__(
        self,
        permission_manager: PermissionManager,
        event_bus: EventBus | None = None,
    ) -> None:
        self._permissions = permission_manager
        self._events = event_bus or EventBus()
        self._tools: dict[str, ToolDescriptor] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._health_checks: dict[str, HealthCheck] = {}
        self._history: list[ToolResult] = []
        self._lock = RLock()

    def register(
        self,
        descriptor: ToolDescriptor,
        handler: ToolHandler,
        *,
        health_check: HealthCheck | None = None,
    ) -> ToolDescriptor:
        self._validate_descriptor(descriptor)
        with self._lock:
            if descriptor.id in self._tools:
                raise ToolError(f"Tool already registered: {descriptor.id}")
            self._tools[descriptor.id] = descriptor
            self._handlers[descriptor.id] = handler
            if health_check is not None:
                self._health_checks[descriptor.id] = health_check
        self._events.publish(
            "ToolRegistered",
            source="neogen.tools",
            payload={"tool_id": descriptor.id, "capabilities": sorted(descriptor.capabilities)},
        )
        return descriptor

    def get(self, tool_id: str) -> ToolDescriptor:
        with self._lock:
            try:
                return self._tools[tool_id]
            except KeyError as exc:
                raise ToolError(f"Unknown tool: {tool_id}") from exc

    def set_enabled(self, tool_id: str, enabled: bool) -> ToolDescriptor:
        with self._lock:
            descriptor = self.get(tool_id)
            updated = replace(descriptor, enabled=enabled)
            self._tools[tool_id] = updated
        self._events.publish(
            "ToolEnabled" if enabled else "ToolDisabled",
            source="neogen.tools",
            payload={"tool_id": tool_id},
        )
        return updated

    def check_health(self, tool_id: str) -> ToolDescriptor:
        with self._lock:
            descriptor = self.get(tool_id)
            check = self._health_checks.get(tool_id)
        if check is None:
            health = ToolHealth.HEALTHY if descriptor.enabled else ToolHealth.UNKNOWN
        else:
            try:
                health = check()
            except Exception:
                health = ToolHealth.UNHEALTHY
        updated = replace(descriptor, health=health)
        with self._lock:
            self._tools[tool_id] = updated
        return updated

    def execute(self, request: ToolRequest) -> ToolResult:
        descriptor = self.get(request.tool_id)
        if not descriptor.enabled:
            raise ToolError(f"Tool is disabled: {request.tool_id}")
        operation = self._required(request.operation, "operation")
        subject = self._required(request.subject_id, "subject_id")
        resource = self._required(request.resource, "resource")
        missing = [
            scope
            for scope in descriptor.required_permissions
            if not self._permissions.has_permission(
                subject_id=subject,
                scope=scope,
                resource=resource,
            )
        ]
        if missing:
            self._events.publish(
                "ToolExecutionDenied",
                source="neogen.tools",
                severity=EventSeverity.WARNING,
                payload={
                    "tool_id": descriptor.id,
                    "operation": operation,
                    "missing_permissions": [scope.value for scope in missing],
                },
                correlation_id=request.correlation_id,
                user_id=subject,
            )
            raise ToolError("Missing permissions: " + ", ".join(scope.value for scope in missing))

        started = perf_counter()
        self._events.publish(
            "ToolExecutionStarted",
            source="neogen.tools",
            payload={"tool_id": descriptor.id, "operation": operation},
            correlation_id=request.correlation_id,
            user_id=subject,
        )
        try:
            output = self._handlers[descriptor.id](request)
            result = ToolResult(
                tool_id=descriptor.id,
                operation=operation,
                success=True,
                output=output,
                duration_ms=(perf_counter() - started) * 1000,
                error=None,
                executed_at=datetime.now(timezone.utc),
            )
            severity = EventSeverity.INFO
        except Exception as exc:  # tool isolation boundary
            result = ToolResult(
                tool_id=descriptor.id,
                operation=operation,
                success=False,
                output=None,
                duration_ms=(perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
                executed_at=datetime.now(timezone.utc),
            )
            severity = EventSeverity.ERROR

        with self._lock:
            self._history.append(result)
        self._events.publish(
            "ToolExecutionCompleted" if result.success else "ToolExecutionFailed",
            source="neogen.tools",
            severity=severity,
            payload={
                "tool_id": descriptor.id,
                "operation": operation,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "error": result.error,
            },
            correlation_id=request.correlation_id,
            user_id=subject,
        )
        return result

    def find(
        self,
        *,
        capability: str | None = None,
        platform: str | None = None,
        enabled_only: bool = True,
    ) -> tuple[ToolDescriptor, ...]:
        normalized_capability = None if capability is None else capability.strip().lower()
        normalized_platform = None if platform is None else platform.strip().lower()
        with self._lock:
            tools = tuple(self._tools.values())
        return tuple(
            tool
            for tool in tools
            if (not enabled_only or tool.enabled)
            and (normalized_capability is None or normalized_capability in tool.capabilities)
            and (normalized_platform is None or normalized_platform in tool.platforms)
        )

    def history(self, *, tool_id: str | None = None, limit: int = 100) -> tuple[ToolResult, ...]:
        if limit <= 0:
            raise ToolError("limit must be positive")
        with self._lock:
            results = self._history if tool_id is None else [item for item in self._history if item.tool_id == tool_id]
            return tuple(results[-limit:])

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "registered": len(self._tools),
                "enabled": sum(1 for tool in self._tools.values() if tool.enabled),
                "healthy": sum(1 for tool in self._tools.values() if tool.health is ToolHealth.HEALTHY),
                "executions": len(self._history),
                "failures": sum(1 for result in self._history if not result.success),
            }

    @classmethod
    def _validate_descriptor(cls, descriptor: ToolDescriptor) -> None:
        cls._required(descriptor.id, "id")
        cls._required(descriptor.name, "name")
        cls._required(descriptor.description, "description")
        if not descriptor.capabilities:
            raise ToolError("At least one tool capability is required")
        if descriptor.timeout_seconds <= 0:
            raise ToolError("timeout_seconds must be positive")
        if not 0.0 <= descriptor.cost_score <= 1.0:
            raise ToolError("cost_score must be between 0 and 1")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ToolError(f"{field} is required")
        return cleaned
