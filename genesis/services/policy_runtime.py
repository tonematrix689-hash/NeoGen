"""Runtime governance primitives for NeoGen.

This module complements the static GovernanceCatalog and the existing
PermissionManager. It models contextual decisions, plugin declarations,
structured audit evidence, and emergency controls without granting any
capability by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Iterable
from uuid import uuid4

from .governance import GovernanceCatalog, RiskLevel


class PermissionState(StrEnum):
    DENIED = "denied"
    ASK_EVERY_TIME = "ask_every_time"
    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"
    ALLOW_PROJECT = "allow_project"
    ALLOW_WORKSPACE = "allow_workspace"
    ALLOW_UNTIL = "allow_until"
    ALWAYS_ALLOW = "always_allow"
    ADMINISTRATOR_ONLY = "administrator_only"
    PROHIBITED = "prohibited"


class EmergencyMode(StrEnum):
    NORMAL = "normal"
    READ_ONLY = "read_only"
    WORKSPACES_LOCKED = "workspaces_locked"
    AGENTS_STOPPED = "agents_stopped"
    FULL_STOP = "full_stop"


@dataclass(frozen=True, slots=True)
class PermissionContext:
    user_id: str
    roles: tuple[str, ...]
    workspace_id: str | None = None
    project_id: str | None = None
    tool_id: str | None = None
    agent_id: str | None = None
    action: str | None = None
    data_classification: str = "internal"
    device_id: str | None = None
    network_id: str | None = None
    session_id: str | None = None
    previous_approval_id: str | None = None
    organization_policy_id: str | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class ContextualDecision:
    id: str
    capability_id: str
    state: PermissionState
    allowed: bool
    requires_approval: bool
    reason: str
    risk_level: int
    minimum_role: str
    context: PermissionContext
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PluginManifest:
    name: str
    version: str
    publisher: str
    required_capabilities: tuple[str, ...]
    supported_actions: tuple[str, ...]
    risk_level: int
    data_accessed: tuple[str, ...] = ()
    network_endpoints: tuple[str, ...] = ()
    audit_behavior: str = "all_actions"
    update_policy: str = "manual_approval"
    removal_procedure: str = "revoke permissions, stop processes, remove files"


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: str
    timestamp: datetime
    user_id: str
    agent_id: str | None
    tool_id: str | None
    permission: str
    action: str
    data_accessed: tuple[str, ...]
    files_affected: tuple[str, ...]
    result: str
    risk_level: int
    approval_status: str
    error_details: str | None
    rollback_status: str
    model: str | None
    provider: str | None
    session_id: str | None
    metadata: dict[str, Any]


@dataclass(slots=True)
class EmergencyState:
    mode: EmergencyMode = EmergencyMode.NORMAL
    terminal_enabled: bool = True
    network_enabled: bool = True
    automation_enabled: bool = True
    workspaces_locked: bool = False
    active_sessions_reset_at: datetime | None = None
    temporary_permissions_revoked_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyRuntime:
    """Evaluate policy context and expose emergency controls.

    This service is intentionally deny-by-default. It does not replace concrete
    user grants; it determines whether an action is eligible to proceed, must
    request approval, or is prohibited by role, risk, or emergency state.
    """

    def __init__(self, catalog: GovernanceCatalog) -> None:
        self._catalog = catalog
        self._plugins: dict[str, PluginManifest] = {}
        self._audit: list[AuditRecord] = []
        self._emergency = EmergencyState()
        self._lock = RLock()

    def evaluate(
        self,
        capability_id: str,
        context: PermissionContext,
        *,
        requested_state: PermissionState = PermissionState.ASK_EVERY_TIME,
        expires_at: datetime | None = None,
    ) -> ContextualDecision:
        policy = self._catalog.get(capability_id)
        minimum_role = self._catalog.decision_requirements(capability_id)["minimum_role"]

        prohibited_reason = self._emergency_prohibition(policy.risk, capability_id)
        if prohibited_reason:
            return self._decision(
                capability_id,
                PermissionState.PROHIBITED,
                False,
                False,
                prohibited_reason,
                policy.risk,
                str(minimum_role),
                context,
            )

        if not self._catalog.role_allows(context.roles, capability_id):
            return self._decision(
                capability_id,
                PermissionState.ADMINISTRATOR_ONLY,
                False,
                False,
                f"Role requirement not met; minimum role is {minimum_role}",
                policy.risk,
                str(minimum_role),
                context,
            )

        if requested_state in {PermissionState.DENIED, PermissionState.PROHIBITED}:
            return self._decision(
                capability_id,
                requested_state,
                False,
                False,
                "Permission state denies the action",
                policy.risk,
                str(minimum_role),
                context,
            )

        if requested_state is PermissionState.ALLOW_UNTIL:
            if expires_at is None or expires_at <= datetime.now(timezone.utc):
                return self._decision(
                    capability_id,
                    PermissionState.DENIED,
                    False,
                    False,
                    "Timed permission is missing or expired",
                    policy.risk,
                    str(minimum_role),
                    context,
                )

        requires_approval = policy.approval_required or policy.risk >= RiskLevel.MEDIUM
        durable_states = {
            PermissionState.ALLOW_PROJECT,
            PermissionState.ALLOW_WORKSPACE,
            PermissionState.ALLOW_UNTIL,
            PermissionState.ALWAYS_ALLOW,
        }
        if policy.risk >= RiskLevel.HIGH and requested_state in durable_states:
            requires_approval = True

        allowed = not requires_approval and requested_state not in {
            PermissionState.ASK_EVERY_TIME,
            PermissionState.ADMINISTRATOR_ONLY,
        }
        reason = "Eligible for execution" if allowed else "Explicit approval required"
        return self._decision(
            capability_id,
            requested_state,
            allowed,
            requires_approval,
            reason,
            policy.risk,
            str(minimum_role),
            context,
            expires_at,
        )

    def register_plugin(self, manifest: PluginManifest) -> PluginManifest:
        if not manifest.name.strip() or not manifest.version.strip() or not manifest.publisher.strip():
            raise ValueError("plugin name, version, and publisher are required")
        for capability_id in manifest.required_capabilities:
            self._catalog.get(capability_id)
        if not 0 <= int(manifest.risk_level) <= 4:
            raise ValueError("plugin risk_level must be between 0 and 4")
        key = f"{manifest.publisher.strip()}::{manifest.name.strip()}"
        with self._lock:
            self._plugins[key] = manifest
        return manifest

    def plugins(self) -> tuple[PluginManifest, ...]:
        with self._lock:
            return tuple(sorted(self._plugins.values(), key=lambda item: (item.publisher, item.name)))

    def record_audit(
        self,
        *,
        user_id: str,
        permission: str,
        action: str,
        result: str,
        risk_level: int,
        agent_id: str | None = None,
        tool_id: str | None = None,
        data_accessed: Iterable[str] = (),
        files_affected: Iterable[str] = (),
        approval_status: str = "not_required",
        error_details: str | None = None,
        rollback_status: str = "not_applicable",
        model: str | None = None,
        provider: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            id=f"audit:{uuid4()}",
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            agent_id=agent_id,
            tool_id=tool_id,
            permission=permission,
            action=action,
            data_accessed=tuple(data_accessed),
            files_affected=tuple(files_affected),
            result=result,
            risk_level=int(risk_level),
            approval_status=approval_status,
            error_details=error_details,
            rollback_status=rollback_status,
            model=model,
            provider=provider,
            session_id=session_id,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._audit.append(record)
        return record

    def audit_records(self, *, limit: int = 250) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(reversed(self._audit[-max(1, limit):]))

    def set_emergency_mode(self, mode: EmergencyMode) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(timezone.utc)
            self._emergency.mode = mode
            self._emergency.updated_at = now
            if mode is EmergencyMode.NORMAL:
                self._emergency.terminal_enabled = True
                self._emergency.network_enabled = True
                self._emergency.automation_enabled = True
                self._emergency.workspaces_locked = False
            elif mode is EmergencyMode.READ_ONLY:
                self._emergency.terminal_enabled = False
                self._emergency.automation_enabled = False
            elif mode is EmergencyMode.WORKSPACES_LOCKED:
                self._emergency.workspaces_locked = True
                self._emergency.terminal_enabled = False
                self._emergency.automation_enabled = False
            elif mode is EmergencyMode.AGENTS_STOPPED:
                self._emergency.automation_enabled = False
            elif mode is EmergencyMode.FULL_STOP:
                self._emergency.terminal_enabled = False
                self._emergency.network_enabled = False
                self._emergency.automation_enabled = False
                self._emergency.workspaces_locked = True
                self._emergency.temporary_permissions_revoked_at = now
                self._emergency.active_sessions_reset_at = now
            return self.emergency_snapshot()

    def emergency_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self._emergency.mode.value,
                "terminal_enabled": self._emergency.terminal_enabled,
                "network_enabled": self._emergency.network_enabled,
                "automation_enabled": self._emergency.automation_enabled,
                "workspaces_locked": self._emergency.workspaces_locked,
                "active_sessions_reset_at": self._iso(self._emergency.active_sessions_reset_at),
                "temporary_permissions_revoked_at": self._iso(
                    self._emergency.temporary_permissions_revoked_at
                ),
                "updated_at": self._emergency.updated_at.isoformat(),
            }

    def snapshot(self) -> dict[str, Any]:
        return {
            "permission_states": [state.value for state in PermissionState],
            "permission_context_fields": [field.name for field in PermissionContext.__dataclass_fields__.values()],
            "plugin_manifest_fields": [field.name for field in PluginManifest.__dataclass_fields__.values()],
            "audit_fields": [field.name for field in AuditRecord.__dataclass_fields__.values()],
            "registered_plugins": [asdict(plugin) for plugin in self.plugins()],
            "audit_count": len(self.audit_records(limit=1_000_000)),
            "emergency": self.emergency_snapshot(),
        }

    def _emergency_prohibition(self, risk: RiskLevel, capability_id: str) -> str | None:
        state = self._emergency
        if state.mode is EmergencyMode.FULL_STOP and capability_id != "chat.use":
            return "NeoGen is in full emergency stop"
        if state.workspaces_locked and capability_id.startswith(("files.", "workspace.", "development.")):
            return "Workspaces are locked"
        if not state.terminal_enabled and capability_id.startswith(("terminal.", "packages.")):
            return "Terminal execution is disabled"
        if not state.network_enabled and capability_id.startswith(("network.", "browser.")):
            return "Network access is disabled"
        if not state.automation_enabled and capability_id.startswith("automation."):
            return "Automation is disabled"
        if state.mode is EmergencyMode.READ_ONLY and risk >= RiskLevel.LOW:
            return "NeoGen is in read-only mode"
        return None

    @staticmethod
    def _decision(
        capability_id: str,
        state: PermissionState,
        allowed: bool,
        requires_approval: bool,
        reason: str,
        risk: RiskLevel,
        minimum_role: str,
        context: PermissionContext,
        expires_at: datetime | None = None,
    ) -> ContextualDecision:
        return ContextualDecision(
            id=f"decision:{uuid4()}",
            capability_id=capability_id,
            state=state,
            allowed=allowed,
            requires_approval=requires_approval,
            reason=reason,
            risk_level=int(risk),
            minimum_role=minimum_role,
            context=context,
            expires_at=expires_at,
        )

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
