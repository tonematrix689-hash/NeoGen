"""Persistent NeoGen Assistant runtime.

This service combines user context, durable memories, plans, approvals and audit
records. Model invocation remains provider-agnostic and is handled by the
conversation/tool layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .events import EventBus
from .permissions import PermissionManager, PermissionScope
from .storage import SQLiteStore


class AssistantError(RuntimeError):
    """Raised when an assistant operation is invalid."""


class AssistantService:
    memory_namespace = "assistant.memories"
    plan_namespace = "assistant.plans"
    audit_namespace = "assistant.audit"
    settings_namespace = "assistant.settings"

    def __init__(
        self,
        store: SQLiteStore,
        permissions: PermissionManager,
        events: EventBus | None = None,
    ) -> None:
        self._store = store
        self._permissions = permissions
        self._events = events or EventBus()

    def remember(
        self,
        user_id: str,
        *,
        title: str,
        content: str,
        category: str = "user",
        importance: float = 0.6,
    ) -> dict[str, Any]:
        cleaned_title = self._required(title, "title")
        cleaned_content = self._required(content, "content")
        score = float(importance)
        if not 0.0 <= score <= 1.0:
            raise AssistantError("importance must be between 0 and 1")
        memory_id = f"memory:{uuid4()}"
        record = {
            "id": memory_id,
            "user_id": user_id,
            "title": cleaned_title,
            "content": cleaned_content,
            "category": self._required(category, "category"),
            "importance": score,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._store.put(self.memory_namespace, memory_id, record)
        self._audit(user_id, "memory.created", {"memory_id": memory_id, "title": cleaned_title})
        return record

    def memories(self, user_id: str, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise AssistantError("limit must be greater than zero")
        records = [
            dict(item.value)
            for item in self._store.list(self.memory_namespace)
            if item.value.get("user_id") == user_id
        ]
        records.sort(
            key=lambda item: (float(item.get("importance", 0)), str(item.get("updated_at", ""))),
            reverse=True,
        )
        return tuple(records[:limit])

    def create_plan(self, user_id: str, *, goal: str) -> dict[str, Any]:
        cleaned_goal = self._required(goal, "goal")
        lower = cleaned_goal.lower()
        steps: list[dict[str, Any]] = []
        if any(word in lower for word in ("file", "code", "build", "create", "edit")):
            steps.append(self._step("inspect_workspace", "Inspect relevant workspace files", PermissionScope.READ_FILES))
            steps.append(self._step("write_workspace", "Create or modify the required files", PermissionScope.WRITE_FILES))
        if any(word in lower for word in ("run", "test", "terminal", "install")):
            steps.append(self._step("run_terminal", "Run approved commands and tests", PermissionScope.RUN_TERMINAL, sensitive=True))
        if any(word in lower for word in ("deploy", "publish", "release")):
            steps.append(self._step("deploy", "Prepare and execute deployment", PermissionScope.DEPLOY, sensitive=True))
        if not steps:
            steps = [
                self._step("understand", "Gather context and constraints", PermissionScope.READ_MEMORY),
                self._step("respond", "Produce the requested result", PermissionScope.USE_MODELS),
            ]

        plan_id = f"plan:{uuid4()}"
        plan = {
            "id": plan_id,
            "user_id": user_id,
            "goal": cleaned_goal,
            "status": "ready",
            "steps": steps,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._store.put(self.plan_namespace, plan_id, plan)
        self._audit(user_id, "plan.created", {"plan_id": plan_id, "goal": cleaned_goal})
        return plan

    def plans(self, user_id: str, *, limit: int = 25) -> tuple[dict[str, Any], ...]:
        records = [
            dict(item.value)
            for item in self._store.list(self.plan_namespace)
            if item.value.get("user_id") == user_id
        ]
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return tuple(records[:limit])

    def set_plan_status(self, user_id: str, plan_id: str, status: str) -> dict[str, Any]:
        allowed = {"ready", "running", "paused", "completed", "cancelled", "failed"}
        if status not in allowed:
            raise AssistantError(f"Unknown plan status: {status}")
        record = dict(self._store.get(self.plan_namespace, plan_id).value)
        if record.get("user_id") != user_id:
            raise AssistantError("Unknown plan")
        record["status"] = status
        record["updated_at"] = self._now()
        self._store.put(self.plan_namespace, plan_id, record)
        self._audit(user_id, "plan.status", {"plan_id": plan_id, "status": status})
        return record

    def approval_summary(self, user_id: str) -> dict[str, Any]:
        pending = self._permissions.pending_requests(user_id)
        grants = self._permissions.active_grants(user_id)
        return {
            "pending": [self._approval_to_dict(item) for item in pending],
            "active_grants": [self._grant_to_dict(item) for item in grants],
        }

    def audit(self, user_id: str, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        records = [
            dict(item.value)
            for item in self._store.list(self.audit_namespace)
            if item.value.get("user_id") == user_id
        ]
        records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return tuple(records[:limit])

    def settings(self, user_id: str) -> dict[str, Any]:
        try:
            return dict(self._store.get(self.settings_namespace, user_id).value)
        except Exception:
            value = {
                "user_id": user_id,
                "assistant_name": "VERA",
                "autonomy": "approval_required",
                "memory_enabled": True,
                "voice_enabled": False,
                "emergency_stop": False,
                "updated_at": self._now(),
            }
            self._store.put(self.settings_namespace, user_id, value)
            return value

    def update_settings(self, user_id: str, values: dict[str, Any]) -> dict[str, Any]:
        current = self.settings(user_id)
        for field in ("assistant_name", "autonomy", "memory_enabled", "voice_enabled", "emergency_stop"):
            if field in values:
                current[field] = values[field]
        if current["autonomy"] not in {"manual", "approval_required", "trusted_safe_actions"}:
            raise AssistantError("Invalid autonomy mode")
        current["assistant_name"] = self._required(str(current["assistant_name"]), "assistant_name")
        current["memory_enabled"] = bool(current["memory_enabled"])
        current["voice_enabled"] = bool(current["voice_enabled"])
        current["emergency_stop"] = bool(current["emergency_stop"])
        current["updated_at"] = self._now()
        self._store.put(self.settings_namespace, user_id, current)
        self._audit(user_id, "settings.updated", {"fields": sorted(values)})
        return current

    def snapshot(self, user_id: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        plans = self.plans(user_id, limit=10)
        return {
            "identity": self.settings(user_id),
            "context": context or {},
            "memories": self.memories(user_id, limit=12),
            "plans": plans,
            "active_plan": next((plan for plan in plans if plan.get("status") in {"ready", "running", "paused"}), None),
            "approvals": self.approval_summary(user_id),
            "audit": self.audit(user_id, limit=20),
        }

    def stats(self) -> dict[str, int]:
        return {
            "memories": len(self._store.list(self.memory_namespace)),
            "plans": len(self._store.list(self.plan_namespace)),
            "audit_records": len(self._store.list(self.audit_namespace)),
            "settings": len(self._store.list(self.settings_namespace)),
        }

    def _audit(self, user_id: str, action: str, details: dict[str, Any]) -> None:
        record_id = f"audit:{uuid4()}"
        record = {
            "id": record_id,
            "user_id": user_id,
            "action": action,
            "details": details,
            "created_at": self._now(),
        }
        self._store.put(self.audit_namespace, record_id, record)
        self._events.publish(
            "AssistantAudit",
            source="neogen.assistant",
            user_id=user_id,
            payload=record,
        )

    @staticmethod
    def _step(step_id: str, title: str, scope: PermissionScope, sensitive: bool = False) -> dict[str, Any]:
        return {
            "id": step_id,
            "title": title,
            "scope": scope.value,
            "status": "pending",
            "sensitive": sensitive,
        }

    @staticmethod
    def _approval_to_dict(item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "scope": item.scope.value,
            "resource": item.resource,
            "reason": item.reason,
            "risk": item.risk,
            "status": item.status.value,
            "requested_at": item.requested_at.isoformat(),
        }

    @staticmethod
    def _grant_to_dict(item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "scope": item.scope.value,
            "resource": item.resource,
            "granted_by": item.granted_by,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise AssistantError(f"{field} is required")
        return cleaned

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
