"""Plugin manifests, lifecycle, permissions, and health management for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Callable, Iterable

from .permissions import PermissionManager, PermissionScope


class PluginError(RuntimeError):
    """Base error for plugin operations."""


class PluginStatus(StrEnum):
    DISCOVERED = "discovered"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    REMOVED = "removed"


class PluginHealth(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    author: str
    description: str
    capabilities: frozenset[str]
    required_permissions: frozenset[PermissionScope]
    entrypoint: str


@dataclass(frozen=True, slots=True)
class PluginRecord:
    manifest: PluginManifest
    status: PluginStatus
    health: PluginHealth
    configuration: dict[str, Any]
    installed_at: datetime | None
    updated_at: datetime
    last_error: str | None = None


PluginHook = Callable[[PluginRecord], None]
HealthCheck = Callable[[PluginRecord], PluginHealth]


class PluginManager:
    """Thread-safe plugin registry with governed lifecycle operations."""

    def __init__(self, permission_manager: PermissionManager | None = None) -> None:
        self._permissions = permission_manager or PermissionManager()
        self._plugins: dict[str, PluginRecord] = {}
        self._hooks: dict[str, dict[str, PluginHook]] = {}
        self._health_checks: dict[str, HealthCheck] = {}
        self._lock = RLock()

    def discover(self, manifest: PluginManifest) -> PluginRecord:
        self._validate_manifest(manifest)
        now = datetime.now(timezone.utc)
        record = PluginRecord(
            manifest=manifest,
            status=PluginStatus.DISCOVERED,
            health=PluginHealth.UNKNOWN,
            configuration={},
            installed_at=None,
            updated_at=now,
        )
        with self._lock:
            if manifest.id in self._plugins and self._plugins[manifest.id].status is not PluginStatus.REMOVED:
                raise PluginError(f"Plugin already exists: {manifest.id}")
            self._plugins[manifest.id] = record
            self._hooks.setdefault(manifest.id, {})
        return record

    def install(self, plugin_id: str, *, subject_id: str, configuration: dict[str, Any] | None = None) -> PluginRecord:
        with self._lock:
            record = self.get(plugin_id)
            if record.status not in {PluginStatus.DISCOVERED, PluginStatus.REMOVED}:
                raise PluginError(f"Plugin cannot be installed from status {record.status.value}")
            self._require_permissions(record, subject_id)
            updated = replace(
                record,
                status=PluginStatus.INSTALLED,
                configuration=dict(configuration or {}),
                installed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                last_error=None,
            )
            self._plugins[plugin_id] = updated
        self._run_hook(plugin_id, "install", updated)
        return updated

    def enable(self, plugin_id: str, *, subject_id: str) -> PluginRecord:
        with self._lock:
            record = self.get(plugin_id)
            if record.status not in {PluginStatus.INSTALLED, PluginStatus.DISABLED, PluginStatus.ERROR}:
                raise PluginError(f"Plugin cannot be enabled from status {record.status.value}")
            self._require_permissions(record, subject_id)
            updated = replace(
                record,
                status=PluginStatus.ENABLED,
                health=PluginHealth.UNKNOWN,
                updated_at=datetime.now(timezone.utc),
                last_error=None,
            )
            self._plugins[plugin_id] = updated
        try:
            self._run_hook(plugin_id, "enable", updated)
            return self.check_health(plugin_id)
        except Exception as exc:
            failed = replace(
                updated,
                status=PluginStatus.ERROR,
                health=PluginHealth.UNHEALTHY,
                updated_at=datetime.now(timezone.utc),
                last_error=f"{type(exc).__name__}: {exc}",
            )
            with self._lock:
                self._plugins[plugin_id] = failed
            return failed

    def disable(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            record = self.get(plugin_id)
            if record.status not in {PluginStatus.ENABLED, PluginStatus.ERROR}:
                raise PluginError(f"Plugin cannot be disabled from status {record.status.value}")
            updated = replace(
                record,
                status=PluginStatus.DISABLED,
                updated_at=datetime.now(timezone.utc),
            )
            self._plugins[plugin_id] = updated
        self._run_hook(plugin_id, "disable", updated)
        return updated

    def remove(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            record = self.get(plugin_id)
            if record.status is PluginStatus.ENABLED:
                raise PluginError("Disable a plugin before removing it")
            updated = replace(
                record,
                status=PluginStatus.REMOVED,
                health=PluginHealth.UNKNOWN,
                updated_at=datetime.now(timezone.utc),
            )
            self._plugins[plugin_id] = updated
        self._run_hook(plugin_id, "remove", updated)
        return updated

    def update_configuration(self, plugin_id: str, configuration: dict[str, Any]) -> PluginRecord:
        with self._lock:
            record = self.get(plugin_id)
            if record.status in {PluginStatus.DISCOVERED, PluginStatus.REMOVED}:
                raise PluginError("Plugin must be installed before configuration")
            updated = replace(
                record,
                configuration=dict(configuration),
                updated_at=datetime.now(timezone.utc),
            )
            self._plugins[plugin_id] = updated
        self._run_hook(plugin_id, "configure", updated)
        return updated

    def register_hook(self, plugin_id: str, event: str, hook: PluginHook) -> None:
        self.get(plugin_id)
        normalized = self._required(event, "event")
        with self._lock:
            self._hooks.setdefault(plugin_id, {})[normalized] = hook

    def register_health_check(self, plugin_id: str, check: HealthCheck) -> None:
        self.get(plugin_id)
        with self._lock:
            self._health_checks[plugin_id] = check

    def check_health(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            record = self.get(plugin_id)
            check = self._health_checks.get(plugin_id)
        if check is None:
            health = PluginHealth.HEALTHY if record.status is PluginStatus.ENABLED else PluginHealth.UNKNOWN
        else:
            try:
                health = check(record)
            except Exception as exc:
                health = PluginHealth.UNHEALTHY
                record = replace(record, last_error=f"{type(exc).__name__}: {exc}")
        updated = replace(record, health=health, updated_at=datetime.now(timezone.utc))
        with self._lock:
            self._plugins[plugin_id] = updated
        return updated

    def get(self, plugin_id: str) -> PluginRecord:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise PluginError(f"Unknown plugin: {plugin_id}") from exc

    def list_plugins(self, *, status: PluginStatus | None = None) -> tuple[PluginRecord, ...]:
        with self._lock:
            records = tuple(self._plugins.values())
        if status is None:
            return records
        return tuple(record for record in records if record.status is status)

    def stats(self) -> dict[str, int]:
        with self._lock:
            result = {status.value: 0 for status in PluginStatus}
            for record in self._plugins.values():
                result[record.status.value] += 1
            result["healthy"] = sum(1 for record in self._plugins.values() if record.health is PluginHealth.HEALTHY)
            result["unhealthy"] = sum(
                1 for record in self._plugins.values() if record.health is PluginHealth.UNHEALTHY
            )
            return result

    def _require_permissions(self, record: PluginRecord, subject_id: str) -> None:
        missing = [
            scope
            for scope in record.manifest.required_permissions
            if not self._permissions.has_permission(
                subject_id=subject_id,
                scope=scope,
                resource=f"plugin:{record.manifest.id}",
            )
        ]
        if missing:
            raise PluginError("Missing permissions: " + ", ".join(scope.value for scope in missing))

    def _run_hook(self, plugin_id: str, event: str, record: PluginRecord) -> None:
        hook = self._hooks.get(plugin_id, {}).get(event)
        if hook is not None:
            hook(record)

    @classmethod
    def _validate_manifest(cls, manifest: PluginManifest) -> None:
        cls._required(manifest.id, "id")
        cls._required(manifest.name, "name")
        cls._required(manifest.version, "version")
        cls._required(manifest.author, "author")
        cls._required(manifest.entrypoint, "entrypoint")
        if not manifest.capabilities:
            raise PluginError("At least one plugin capability is required")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise PluginError(f"{field} is required")
        return cleaned
