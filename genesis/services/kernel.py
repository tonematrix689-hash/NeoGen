"""Unified composition root for NeoGen intelligent services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .agents import AgentManager
from .checkpoints import CheckpointManager
from .conversations import ConversationService
from .events import EventBus
from .game import GameService
from .identity import IdentityService
from .investment import RegenerativeInvestmentService
from .legal import LegalService
from .memory import MemoryEngine
from .models import ModelRouter
from .permissions import PermissionManager
from .planning import PlanningEngine
from .plugins import PluginManager
from .projects import ProjectIntelligence
from .puter import register_puter_provider
from .storage import SQLiteStore
from .subscriptions import SubscriptionService
from .terminal import TerminalService
from .tools import ToolRegistry
from .verification import VerificationEngine
from .workspace import WorkspaceService
from .workflows import WorkflowEngine


@dataclass(slots=True)
class NeoGenKernel:
    events: EventBus
    storage: SQLiteStore
    checkpoints: CheckpointManager
    identity: IdentityService
    permissions: PermissionManager
    memory: MemoryEngine
    agents: AgentManager
    workflows: WorkflowEngine
    models: ModelRouter
    plugins: PluginManager
    projects: ProjectIntelligence
    tools: ToolRegistry
    conversations: ConversationService
    workspace: WorkspaceService
    terminal: TerminalService
    game: GameService
    planning: PlanningEngine
    verification: VerificationEngine
    subscriptions: SubscriptionService
    legal: LegalService
    investment: RegenerativeInvestmentService

    @classmethod
    def build(
        cls,
        *,
        enable_puter: bool = True,
        storage_path: str | Path = ":memory:",
        workspace_path: str | Path = "workspace",
    ) -> "NeoGenKernel":
        events = EventBus()
        storage = SQLiteStore(storage_path)
        checkpoints = CheckpointManager(storage, events)
        identity = IdentityService(storage, events)
        permissions = PermissionManager()
        memory = MemoryEngine()
        agents = AgentManager(permissions)
        workflows = WorkflowEngine(agents, permissions)
        models = ModelRouter()
        plugins = PluginManager(permissions)
        projects = ProjectIntelligence()
        tools = ToolRegistry(permissions, events)
        conversations = ConversationService(storage, tools, events)
        workspace = WorkspaceService(workspace_path, events)
        terminal = TerminalService(workspace.root, events)
        game = GameService(storage, events)
        planning = PlanningEngine(permissions, tools, events)
        verification = VerificationEngine(events)
        subscriptions = SubscriptionService(storage, events)
        legal = LegalService(storage, events)
        investment = RegenerativeInvestmentService()

        if enable_puter:
            register_puter_provider(tools, permissions, events)

        kernel = cls(
            events=events,
            storage=storage,
            checkpoints=checkpoints,
            identity=identity,
            permissions=permissions,
            memory=memory,
            agents=agents,
            workflows=workflows,
            models=models,
            plugins=plugins,
            projects=projects,
            tools=tools,
            conversations=conversations,
            workspace=workspace,
            terminal=terminal,
            game=game,
            planning=planning,
            verification=verification,
            subscriptions=subscriptions,
            legal=legal,
            investment=investment,
        )
        kernel.events.publish(
            "KernelBuilt",
            source="neogen.kernel",
            payload={
                "services": list(kernel.health().keys()),
                "puter_enabled": enable_puter,
                "storage_backend": kernel.storage.stats()["backend"],
                "workspace_root": str(kernel.workspace.root),
            },
        )
        return kernel

    def checkpoint(self, *, category: str, subject_id: str, state: object) -> str:
        return self.checkpoints.save(category=category, subject_id=subject_id, state=state).id

    def close(self) -> None:
        self.storage.close()

    def health(self) -> dict[str, dict[str, int | str] | str]:
        return {
            "status": "healthy",
            "storage": self.storage.stats(),
            "checkpoints": self.checkpoints.stats(),
            "identity": self.identity.stats(),
            "conversations": self.conversations.stats(),
            "workspace": self.workspace.stats(),
            "terminal": self.terminal.stats(),
            "game": self.game.stats(),
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
            "subscriptions": self.subscriptions.stats(),
            "legal": self.legal.stats(),
            "investment": self.investment.stats(),
        }
