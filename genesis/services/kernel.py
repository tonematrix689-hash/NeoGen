"""Unified composition root for NeoGen intelligent services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .agents import AgentManager
from .checkpoints import CheckpointManager
from .events import EventBus
from .memory import MemoryEngine
from .models import ModelRouter
from .permissions import PermissionManager
from .planning import PlanningEngine
from .plugins import PluginManager
from .projects import ProjectIntelligence
from .puter import register_puter_provider
from .storage import SQLiteStore
from .tools import ToolRegistry
from .verification import VerificationEngine
from .workflows import WorkflowEngine


@dataclass(slots=True)
class NeoGenKernel:
    """Own and expose the core intelligent services as one cohesive kernel."""

    events: EventBus
    storage: SQLiteStore
    checkpoints: CheckpointManager
    permissions: PermissionManager
    memory: MemoryEngine
    agents: AgentManager
    workflows: WorkflowEngine
    models: ModelRouter
    plugins: PluginManager
    projects: ProjectIntelligence
    tools: ToolRegistry
    planning: PlanningEngine
    verification: VerificationEngine

    @classmethod
    def build(
        cls,
        *,
        enable_puter: bool = True,
        storage_path: str | Path = ":memory:",
    ) -> "NeoGenKernel":
        events = EventBus()
        storage = SQLiteStore(storage_path)
        checkpoints = CheckpointManager(storage, events)
        permissions = PermissionManager()
        memory = MemoryEngine()
        agents = AgentManager(permissions)
        workflows = WorkflowEngine(agents, permissions)
        models = ModelRouter()
        plugins = PluginManager(permissions)
        projects = ProjectIntelligence()
        tools = ToolRegistry(permissions, events)
        planning = PlanningEngine(permissions, tools, events)
        verification = VerificationEngine(events)

        if enable_puter:
            register_puter_provider(tools, permissions, events)

        kernel = cls(
            events=events,
            storage=storage,
            checkpoints=checkpoints,
            permissions=permissions,
            memory=memory,
            agents=agents,
            workflows=workflows,
            models=models,
            plugins=plugins,
            projects=projects,
            tools=tools,
            planning=planning,
            verification=verification,
        )
        kernel.events.publish(
            "KernelBuilt",
            source="neogen.kernel",
            payload={
                "services": list(kernel.health().keys()),
                "puter_enabled": enable_puter,
                "storage_backend": kernel.storage.stats()["backend"],
            },
        )
        return kernel

    def checkpoint(self, *, category: str, subject_id: str, state: object) -> str:
        """Persist a restart-safe kernel state snapshot and return its ID."""

        return self.checkpoints.save(
            category=category,
            subject_id=subject_id,
            state=state,
        ).id

    def close(self) -> None:
        """Release durable resources owned by the kernel."""

        self.storage.close()

    def health(self) -> dict[str, dict[str, int | str] | str]:
        """Return a consolidated, serializable health snapshot."""

        return {
            "status": "healthy",
            "storage": self.storage.stats(),
            "checkpoints": self.checkpoints.stats(),
            "events": self.events.stats(),
            "permissions": self.permissions.stats(),
            "memory": self.memory.stats(),
            "agents": self.agents.stats(),
            "workflows": self.workflows.stats(),
            "models": {"registered": len(self.models.metrics())},
            "plugins": self.plugins.stats(),
            "projects": {"service_available": 1},
            "tools": self.tools.stats(),
            "planning": self.planning.stats(),
            "verification": self.verification.stats(),
        }
