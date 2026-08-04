"""Goal decomposition, risk scoring, and executable plan generation for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Iterable
from uuid import uuid4

from .events import EventBus
from .permissions import PermissionManager, PermissionScope
from .tools import ToolRegistry


class PlanningError(RuntimeError):
    """Base error for planning operations."""


class PlanStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepKind(StrEnum):
    ANALYZE = "analyze"
    RETRIEVE = "retrieve"
    MODEL = "model"
    AGENT = "agent"
    TOOL = "tool"
    VERIFY = "verify"
    APPROVAL = "approval"


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: str
    name: str
    kind: StepKind
    description: str
    dependencies: frozenset[str]
    required_permissions: frozenset[PermissionScope]
    resource: str
    tool_id: str | None
    estimated_cost: float
    estimated_seconds: float
    risk: float
    verification: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    id: str
    subject_id: str
    goal: str
    success_criteria: tuple[str, ...]
    constraints: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    status: PlanStatus
    risk: float
    estimated_cost: float
    estimated_seconds: float
    missing_permissions: frozenset[PermissionScope]
    created_at: datetime


class PlanningEngine:
    """Build and validate permission-aware execution plans."""

    HIGH_RISK_THRESHOLD = 0.7

    def __init__(
        self,
        permission_manager: PermissionManager,
        tool_registry: ToolRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self._permissions = permission_manager
        self._tools = tool_registry
        self._events = event_bus or EventBus()
        self._plans: dict[str, ExecutionPlan] = {}
        self._lock = RLock()

    def make_step(
        self,
        *,
        name: str,
        kind: StepKind,
        description: str,
        dependencies: Iterable[str] = (),
        required_permissions: Iterable[PermissionScope] = (),
        resource: str = "*",
        tool_id: str | None = None,
        estimated_cost: float = 0.0,
        estimated_seconds: float = 0.0,
        risk: float = 0.0,
        verification: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PlanStep:
        if tool_id is not None:
            self._tools.get(tool_id)
        return PlanStep(
            id=f"plan-step:{uuid4()}",
            name=self._required(name, "name"),
            kind=kind,
            description=self._required(description, "description"),
            dependencies=frozenset(dependencies),
            required_permissions=frozenset(required_permissions),
            resource=self._required(resource, "resource"),
            tool_id=tool_id,
            estimated_cost=self._nonnegative(estimated_cost, "estimated_cost"),
            estimated_seconds=self._nonnegative(estimated_seconds, "estimated_seconds"),
            risk=self._score(risk, "risk"),
            verification=None if verification is None else self._required(verification, "verification"),
            metadata=dict(metadata or {}),
        )

    def create_plan(
        self,
        *,
        subject_id: str,
        goal: str,
        steps: Iterable[PlanStep],
        success_criteria: Iterable[str] = (),
        constraints: Iterable[str] = (),
    ) -> ExecutionPlan:
        ordered = tuple(steps)
        if not ordered:
            raise PlanningError("A plan must contain at least one step")
        self._validate_dependencies(ordered)
        subject = self._required(subject_id, "subject_id")
        criteria = tuple(self._required(value, "success_criterion") for value in success_criteria)
        plan_risk = max(step.risk for step in ordered)
        missing = self._missing_permissions(subject, ordered)
        status = self._derive_status(plan_risk, missing)
        plan = ExecutionPlan(
            id=f"plan:{uuid4()}",
            subject_id=subject,
            goal=self._required(goal, "goal"),
            success_criteria=criteria,
            constraints=tuple(self._required(value, "constraint") for value in constraints),
            steps=ordered,
            status=status,
            risk=plan_risk,
            estimated_cost=sum(step.estimated_cost for step in ordered),
            estimated_seconds=sum(step.estimated_seconds for step in ordered),
            missing_permissions=frozenset(missing),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._plans[plan.id] = plan
        self._events.publish(
            "PlanCreated",
            source="neogen.planning",
            payload={
                "plan_id": plan.id,
                "goal": plan.goal,
                "status": plan.status.value,
                "risk": plan.risk,
                "step_count": len(plan.steps),
            },
            user_id=subject,
        )
        return plan

    def get(self, plan_id: str) -> ExecutionPlan:
        with self._lock:
            try:
                return self._plans[plan_id]
            except KeyError as exc:
                raise PlanningError(f"Unknown plan: {plan_id}") from exc

    def validate(self, plan_id: str) -> ExecutionPlan:
        plan = self.get(plan_id)
        self._validate_dependencies(plan.steps)
        missing = self._missing_permissions(plan.subject_id, plan.steps)
        status = self._derive_status(plan.risk, missing)
        updated = ExecutionPlan(
            id=plan.id,
            subject_id=plan.subject_id,
            goal=plan.goal,
            success_criteria=plan.success_criteria,
            constraints=plan.constraints,
            steps=plan.steps,
            status=status,
            risk=plan.risk,
            estimated_cost=plan.estimated_cost,
            estimated_seconds=plan.estimated_seconds,
            missing_permissions=frozenset(missing),
            created_at=plan.created_at,
        )
        with self._lock:
            self._plans[plan.id] = updated
        return updated

    def approval_requests(self, plan_id: str, *, reason: str | None = None) -> tuple[str, ...]:
        plan = self.get(plan_id)
        request_ids: list[str] = []
        for scope in sorted(plan.missing_permissions, key=lambda item: item.value):
            resource = next(
                step.resource for step in plan.steps if scope in step.required_permissions
            )
            request = self._permissions.request(
                subject_id=plan.subject_id,
                scope=scope,
                resource=resource,
                reason=reason or f"Approval required for plan: {plan.goal}",
                risk=plan.risk,
            )
            request_ids.append(request.id)
        return tuple(request_ids)

    def plans(self, *, status: PlanStatus | None = None) -> tuple[ExecutionPlan, ...]:
        with self._lock:
            values = tuple(self._plans.values())
        if status is None:
            return values
        return tuple(plan for plan in values if plan.status is status)

    def stats(self) -> dict[str, int]:
        with self._lock:
            result = {status.value: 0 for status in PlanStatus}
            for plan in self._plans.values():
                result[plan.status.value] += 1
            result["total"] = len(self._plans)
            return result

    def _missing_permissions(
        self,
        subject_id: str,
        steps: tuple[PlanStep, ...],
    ) -> set[PermissionScope]:
        missing: set[PermissionScope] = set()
        for step in steps:
            for scope in step.required_permissions:
                if not self._permissions.has_permission(
                    subject_id=subject_id,
                    scope=scope,
                    resource=step.resource,
                ):
                    missing.add(scope)
        return missing

    @classmethod
    def _derive_status(
        cls,
        risk: float,
        missing: set[PermissionScope],
    ) -> PlanStatus:
        if missing or risk >= cls.HIGH_RISK_THRESHOLD:
            return PlanStatus.APPROVAL_REQUIRED
        return PlanStatus.READY

    @staticmethod
    def _validate_dependencies(steps: tuple[PlanStep, ...]) -> None:
        ids = {step.id for step in steps}
        if len(ids) != len(steps):
            raise PlanningError("Plan step IDs must be unique")
        seen: set[str] = set()
        for step in steps:
            unknown = step.dependencies - ids
            if unknown:
                raise PlanningError(f"Unknown dependencies for {step.name}: {sorted(unknown)}")
            if step.id in step.dependencies:
                raise PlanningError(f"Step cannot depend on itself: {step.name}")
            if not step.dependencies.issubset(seen):
                raise PlanningError(f"Dependencies must appear before step: {step.name}")
            seen.add(step.id)

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise PlanningError(f"{field} is required")
        return cleaned

    @staticmethod
    def _score(value: float, field: str) -> float:
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise PlanningError(f"{field} must be between 0 and 1")
        return score

    @staticmethod
    def _nonnegative(value: float, field: str) -> float:
        number = float(value)
        if number < 0:
            raise PlanningError(f"{field} cannot be negative")
        return number
