"""Agent registration, task queues, and execution tracking for NeoGen."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Callable, Iterable
from uuid import uuid4

from .permissions import PermissionManager, PermissionScope


class AgentError(RuntimeError):
    """Base error for agent operations."""


class AgentStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    id: str
    name: str
    capabilities: frozenset[str]
    required_permissions: frozenset[PermissionScope]
    status: AgentStatus
    current_task_id: str | None
    completed_tasks: int
    failed_tasks: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AgentTask:
    id: str
    agent_id: str
    name: str
    payload: dict[str, Any]
    required_permissions: frozenset[PermissionScope]
    resource: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any = None
    error: str | None = None


AgentHandler = Callable[[AgentTask], Any]


class AgentManager:
    """Thread-safe registry and FIFO task executor for NeoGen agents."""

    def __init__(self, permission_manager: PermissionManager | None = None) -> None:
        self._permissions = permission_manager or PermissionManager()
        self._agents: dict[str, AgentDescriptor] = {}
        self._handlers: dict[str, AgentHandler] = {}
        self._tasks: dict[str, AgentTask] = {}
        self._queues: dict[str, deque[str]] = {}
        self._lock = RLock()

    def register(
        self,
        *,
        name: str,
        capabilities: Iterable[str] = (),
        required_permissions: Iterable[PermissionScope] = (),
        handler: AgentHandler | None = None,
    ) -> AgentDescriptor:
        normalized_name = self._required(name, "name")
        now = datetime.now(timezone.utc)
        agent = AgentDescriptor(
            id=f"agent:{uuid4()}",
            name=normalized_name,
            capabilities=self._normalize(capabilities),
            required_permissions=frozenset(required_permissions),
            status=AgentStatus.IDLE,
            current_task_id=None,
            completed_tasks=0,
            failed_tasks=0,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._agents[agent.id] = agent
            self._queues[agent.id] = deque()
            if handler is not None:
                self._handlers[agent.id] = handler
        return agent

    def get_agent(self, agent_id: str) -> AgentDescriptor:
        with self._lock:
            try:
                return self._agents[agent_id]
            except KeyError as exc:
                raise AgentError(f"Unknown agent: {agent_id}") from exc

    def set_handler(self, agent_id: str, handler: AgentHandler) -> None:
        self.get_agent(agent_id)
        with self._lock:
            self._handlers[agent_id] = handler

    def pause(self, agent_id: str) -> AgentDescriptor:
        return self._set_status(agent_id, AgentStatus.PAUSED)

    def resume(self, agent_id: str) -> AgentDescriptor:
        agent = self.get_agent(agent_id)
        if agent.status is AgentStatus.STOPPED:
            raise AgentError("Stopped agents cannot be resumed")
        return self._set_status(agent_id, AgentStatus.IDLE)

    def stop(self, agent_id: str) -> AgentDescriptor:
        with self._lock:
            agent = self.get_agent(agent_id)
            queue = self._queues[agent_id]
            while queue:
                task_id = queue.popleft()
                task = self._tasks[task_id]
                self._tasks[task_id] = replace(
                    task,
                    status=TaskStatus.CANCELLED,
                    finished_at=datetime.now(timezone.utc),
                    error="Agent stopped before execution",
                )
            stopped = replace(
                agent,
                status=AgentStatus.STOPPED,
                current_task_id=None,
                updated_at=datetime.now(timezone.utc),
            )
            self._agents[agent_id] = stopped
            return stopped

    def enqueue(
        self,
        *,
        agent_id: str,
        name: str,
        payload: dict[str, Any] | None = None,
        required_permissions: Iterable[PermissionScope] = (),
        resource: str = "*",
    ) -> AgentTask:
        agent = self.get_agent(agent_id)
        if agent.status is AgentStatus.STOPPED:
            raise AgentError("Cannot queue work for a stopped agent")
        task = AgentTask(
            id=f"task:{uuid4()}",
            agent_id=agent_id,
            name=self._required(name, "name"),
            payload=dict(payload or {}),
            required_permissions=frozenset(required_permissions),
            resource=self._required(resource, "resource"),
            status=TaskStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._tasks[task.id] = task
            self._queues[agent_id].append(task.id)
        return task

    def run_next(self, agent_id: str) -> AgentTask | None:
        with self._lock:
            agent = self.get_agent(agent_id)
            if agent.status in {AgentStatus.PAUSED, AgentStatus.STOPPED}:
                return None
            queue = self._queues[agent_id]
            if not queue:
                return None
            task_id = queue.popleft()
            task = self._tasks[task_id]

            permissions = agent.required_permissions | task.required_permissions
            missing = [
                scope
                for scope in permissions
                if not self._permissions.has_permission(
                    subject_id=agent_id,
                    scope=scope,
                    resource=task.resource,
                )
            ]
            if missing:
                blocked = replace(
                    task,
                    status=TaskStatus.BLOCKED,
                    finished_at=datetime.now(timezone.utc),
                    error="Missing permissions: " + ", ".join(scope.value for scope in missing),
                )
                self._tasks[task_id] = blocked
                return blocked

            handler = self._handlers.get(agent_id)
            if handler is None:
                failed = replace(
                    task,
                    status=TaskStatus.FAILED,
                    finished_at=datetime.now(timezone.utc),
                    error="No handler registered",
                )
                self._tasks[task_id] = failed
                self._agents[agent_id] = replace(
                    agent,
                    status=AgentStatus.ERROR,
                    failed_tasks=agent.failed_tasks + 1,
                    updated_at=datetime.now(timezone.utc),
                )
                return failed

            running_task = replace(task, status=TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))
            self._tasks[task_id] = running_task
            self._agents[agent_id] = replace(
                agent,
                status=AgentStatus.RUNNING,
                current_task_id=task_id,
                updated_at=datetime.now(timezone.utc),
            )

        try:
            result = handler(running_task)
        except Exception as exc:  # execution boundary
            with self._lock:
                failed = replace(
                    running_task,
                    status=TaskStatus.FAILED,
                    finished_at=datetime.now(timezone.utc),
                    error=f"{type(exc).__name__}: {exc}",
                )
                self._tasks[task_id] = failed
                current = self._agents[agent_id]
                self._agents[agent_id] = replace(
                    current,
                    status=AgentStatus.ERROR,
                    current_task_id=None,
                    failed_tasks=current.failed_tasks + 1,
                    updated_at=datetime.now(timezone.utc),
                )
                return failed

        with self._lock:
            completed = replace(
                running_task,
                status=TaskStatus.COMPLETED,
                finished_at=datetime.now(timezone.utc),
                result=result,
            )
            self._tasks[task_id] = completed
            current = self._agents[agent_id]
            self._agents[agent_id] = replace(
                current,
                status=AgentStatus.IDLE,
                current_task_id=None,
                completed_tasks=current.completed_tasks + 1,
                updated_at=datetime.now(timezone.utc),
            )
            return completed

    def run_all(self, agent_id: str) -> tuple[AgentTask, ...]:
        completed: list[AgentTask] = []
        while True:
            task = self.run_next(agent_id)
            if task is None:
                break
            completed.append(task)
        return tuple(completed)

    def task(self, task_id: str) -> AgentTask:
        with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as exc:
                raise AgentError(f"Unknown task: {task_id}") from exc

    def queue(self, agent_id: str) -> tuple[AgentTask, ...]:
        self.get_agent(agent_id)
        with self._lock:
            return tuple(self._tasks[task_id] for task_id in self._queues[agent_id])

    def agents(self) -> tuple[AgentDescriptor, ...]:
        with self._lock:
            return tuple(self._agents.values())

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "agents": len(self._agents),
                "queued": sum(len(queue) for queue in self._queues.values()),
                "completed": sum(1 for task in self._tasks.values() if task.status is TaskStatus.COMPLETED),
                "failed": sum(1 for task in self._tasks.values() if task.status is TaskStatus.FAILED),
                "blocked": sum(1 for task in self._tasks.values() if task.status is TaskStatus.BLOCKED),
            }

    def _set_status(self, agent_id: str, status: AgentStatus) -> AgentDescriptor:
        with self._lock:
            agent = self.get_agent(agent_id)
            updated = replace(agent, status=status, updated_at=datetime.now(timezone.utc))
            self._agents[agent_id] = updated
            return updated

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise AgentError(f"{field} is required")
        return cleaned

    @staticmethod
    def _normalize(values: Iterable[str]) -> frozenset[str]:
        return frozenset(value.strip().lower() for value in values if value.strip())
