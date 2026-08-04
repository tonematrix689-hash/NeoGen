"""Permission-aware workflow orchestration for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Iterable
from uuid import uuid4

from .agents import AgentManager, AgentTask, TaskStatus
from .permissions import PermissionManager, PermissionScope


class WorkflowError(RuntimeError):
    """Base error for workflow operations."""


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    id: str
    name: str
    agent_id: str
    task_name: str
    payload: dict[str, Any]
    required_permissions: frozenset[PermissionScope]
    resource: str
    max_retries: int
    approval_required: bool


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    id: str
    name: str
    description: str
    steps: tuple[WorkflowStep, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StepExecution:
    step_id: str
    status: StepStatus
    attempts: int
    task_id: str | None = None
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: str
    workflow_id: str
    subject_id: str
    status: WorkflowStatus
    step_executions: tuple[StepExecution, ...]
    current_step: int
    created_at: datetime
    updated_at: datetime


class WorkflowEngine:
    """Runs ordered workflows using the Agent Manager and Permission Manager."""

    def __init__(
        self,
        agent_manager: AgentManager,
        permission_manager: PermissionManager,
    ) -> None:
        self._agents = agent_manager
        self._permissions = permission_manager
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._runs: dict[str, WorkflowRun] = {}
        self._lock = RLock()

    def define(
        self,
        *,
        name: str,
        description: str = "",
        steps: Iterable[WorkflowStep],
    ) -> WorkflowDefinition:
        ordered = tuple(steps)
        if not ordered:
            raise WorkflowError("A workflow must contain at least one step")
        if len({step.id for step in ordered}) != len(ordered):
            raise WorkflowError("Workflow step IDs must be unique")
        definition = WorkflowDefinition(
            id=f"workflow:{uuid4()}",
            name=self._required(name, "name"),
            description=description.strip(),
            steps=ordered,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._definitions[definition.id] = definition
        return definition

    def make_step(
        self,
        *,
        name: str,
        agent_id: str,
        task_name: str,
        payload: dict[str, Any] | None = None,
        required_permissions: Iterable[PermissionScope] = (),
        resource: str = "*",
        max_retries: int = 0,
        approval_required: bool = False,
    ) -> WorkflowStep:
        self._agents.get_agent(agent_id)
        if max_retries < 0:
            raise WorkflowError("max_retries cannot be negative")
        return WorkflowStep(
            id=f"step:{uuid4()}",
            name=self._required(name, "name"),
            agent_id=agent_id,
            task_name=self._required(task_name, "task_name"),
            payload=dict(payload or {}),
            required_permissions=frozenset(required_permissions),
            resource=self._required(resource, "resource"),
            max_retries=max_retries,
            approval_required=approval_required,
        )

    def start(self, workflow_id: str, *, subject_id: str) -> WorkflowRun:
        definition = self.get_definition(workflow_id)
        now = datetime.now(timezone.utc)
        run = WorkflowRun(
            id=f"run:{uuid4()}",
            workflow_id=definition.id,
            subject_id=self._required(subject_id, "subject_id"),
            status=WorkflowStatus.RUNNING,
            step_executions=tuple(
                StepExecution(step_id=step.id, status=StepStatus.PENDING, attempts=0)
                for step in definition.steps
            ),
            current_step=0,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._runs[run.id] = run
        return run

    def advance(self, run_id: str) -> WorkflowRun:
        with self._lock:
            run = self.get_run(run_id)
            if run.status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}:
                return run
            definition = self.get_definition(run.workflow_id)
            if run.current_step >= len(definition.steps):
                completed = replace(run, status=WorkflowStatus.COMPLETED, updated_at=datetime.now(timezone.utc))
                self._runs[run_id] = completed
                return completed
            step = definition.steps[run.current_step]
            execution = run.step_executions[run.current_step]

        if step.approval_required:
            decision = self._permissions.evaluate(
                subject_id=run.subject_id,
                scope=next(iter(step.required_permissions), PermissionScope.ADMIN),
                resource=step.resource,
                reason=f"Workflow step approval: {step.name}",
                risk=0.8,
                auto_request=True,
            )
            if not decision.allowed:
                waiting_execution = replace(execution, status=StepStatus.WAITING_APPROVAL)
                waiting_run = self._replace_execution(
                    run,
                    waiting_execution,
                    status=WorkflowStatus.WAITING_APPROVAL,
                )
                with self._lock:
                    self._runs[run_id] = waiting_run
                return waiting_run

        queued = self._agents.enqueue(
            agent_id=step.agent_id,
            name=step.task_name,
            payload=step.payload,
            required_permissions=step.required_permissions,
            resource=step.resource,
        )
        running_execution = replace(
            execution,
            status=StepStatus.RUNNING,
            attempts=execution.attempts + 1,
            task_id=queued.id,
            started_at=datetime.now(timezone.utc),
        )
        with self._lock:
            running_run = self._replace_execution(run, running_execution, status=WorkflowStatus.RUNNING)
            self._runs[run_id] = running_run

        task = self._agents.run_next(step.agent_id)
        if task is None:
            raise WorkflowError("Agent did not execute queued workflow task")
        return self._apply_task_result(running_run, step, running_execution, task)

    def run_to_completion(self, run_id: str, *, max_transitions: int = 100) -> WorkflowRun:
        if max_transitions <= 0:
            raise WorkflowError("max_transitions must be positive")
        run = self.get_run(run_id)
        for _ in range(max_transitions):
            if run.status in {
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED,
                WorkflowStatus.WAITING_APPROVAL,
            }:
                return run
            run = self.advance(run.id)
        raise WorkflowError("Workflow exceeded transition limit")

    def resume(self, run_id: str) -> WorkflowRun:
        with self._lock:
            run = self.get_run(run_id)
            if run.status is not WorkflowStatus.WAITING_APPROVAL:
                raise WorkflowError("Only workflows waiting for approval can be resumed")
            definition = self.get_definition(run.workflow_id)
            step = definition.steps[run.current_step]
            missing = [
                scope
                for scope in step.required_permissions
                if not self._permissions.has_permission(
                    subject_id=run.subject_id,
                    scope=scope,
                    resource=step.resource,
                )
            ]
            if missing:
                raise WorkflowError("Required approval has not been granted")
            pending_execution = replace(
                run.step_executions[run.current_step],
                status=StepStatus.PENDING,
            )
            resumed = self._replace_execution(run, pending_execution, status=WorkflowStatus.RUNNING)
            self._runs[run_id] = resumed
            return resumed

    def cancel(self, run_id: str) -> WorkflowRun:
        with self._lock:
            run = self.get_run(run_id)
            cancelled = replace(run, status=WorkflowStatus.CANCELLED, updated_at=datetime.now(timezone.utc))
            self._runs[run_id] = cancelled
            return cancelled

    def get_definition(self, workflow_id: str) -> WorkflowDefinition:
        with self._lock:
            try:
                return self._definitions[workflow_id]
            except KeyError as exc:
                raise WorkflowError(f"Unknown workflow: {workflow_id}") from exc

    def get_run(self, run_id: str) -> WorkflowRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise WorkflowError(f"Unknown workflow run: {run_id}") from exc

    def runs(self) -> tuple[WorkflowRun, ...]:
        with self._lock:
            return tuple(self._runs.values())

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "definitions": len(self._definitions),
                "runs": len(self._runs),
                "running": sum(1 for run in self._runs.values() if run.status is WorkflowStatus.RUNNING),
                "waiting_approval": sum(
                    1 for run in self._runs.values() if run.status is WorkflowStatus.WAITING_APPROVAL
                ),
                "completed": sum(1 for run in self._runs.values() if run.status is WorkflowStatus.COMPLETED),
                "failed": sum(1 for run in self._runs.values() if run.status is WorkflowStatus.FAILED),
            }

    def _apply_task_result(
        self,
        run: WorkflowRun,
        step: WorkflowStep,
        execution: StepExecution,
        task: AgentTask,
    ) -> WorkflowRun:
        if task.status is TaskStatus.COMPLETED:
            completed_execution = replace(
                execution,
                status=StepStatus.COMPLETED,
                result=task.result,
                finished_at=datetime.now(timezone.utc),
            )
            next_index = run.current_step + 1
            status = WorkflowStatus.COMPLETED if next_index >= len(self.get_definition(run.workflow_id).steps) else WorkflowStatus.RUNNING
            updated = self._replace_execution(
                run,
                completed_execution,
                status=status,
                current_step=next_index,
            )
        else:
            can_retry = execution.attempts <= step.max_retries
            failed_execution = replace(
                execution,
                status=StepStatus.PENDING if can_retry else StepStatus.FAILED,
                error=task.error or task.status.value,
                finished_at=None if can_retry else datetime.now(timezone.utc),
            )
            updated = self._replace_execution(
                run,
                failed_execution,
                status=WorkflowStatus.RUNNING if can_retry else WorkflowStatus.FAILED,
            )
        with self._lock:
            self._runs[run.id] = updated
        return updated

    @staticmethod
    def _replace_execution(
        run: WorkflowRun,
        execution: StepExecution,
        *,
        status: WorkflowStatus,
        current_step: int | None = None,
    ) -> WorkflowRun:
        executions = list(run.step_executions)
        executions[run.current_step] = execution
        return replace(
            run,
            status=status,
            step_executions=tuple(executions),
            current_step=run.current_step if current_step is None else current_step,
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise WorkflowError(f"{field} is required")
        return cleaned
