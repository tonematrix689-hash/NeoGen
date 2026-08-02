"""Unified composition root for NeoGen intelligent services."""

from __future__ import annotations

from dataclasses import dataclass

from .agents import AgentManager
from .events import EventBus
from .memory import MemoryEngine
from .models import ModelRouter
from .permissions import PermissionManager
from .planning import PlanningEngine
from .plugins import PluginManager
from .projects import ProjectIntelligence
from .puter import register_puter_provider
from .tools import ToolRegistry
from .verification import VerificationEngine
from .workflows import WorkflowEngine


@dataclass(slots=True)
class NeoGenKernel:
    """Own and expose the core intelligent services as one cohesive kernel."""

    events: EventBus
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
    def build(cls, *, enable_puter: bool = True) -> "NeoGenKernel":
        events = EventBus()
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
            },
        )
        return kernel

    def health(self) -> dict[str, dict[str, int] | str]:
        """Return a consolidated, serializable health snapshot."""

        return {
            "status": "healthy",
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
