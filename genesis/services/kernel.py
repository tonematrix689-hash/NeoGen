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
from .memory import MemoryEngine
from .models import ModelRouter
from .permissions import PermissionManager
from .planning import PlanningEngine
from .plugins import PluginManager
from .projects import ProjectIntelligence
from .puter import register_puter_provider
from .storage import SQLiteStore
from .terminal import TerminalService
from .tools import ToolRegistry
from .verification import VerificationEngine
from .workspace import WorkspaceService
from .workflows import WorkflowEngine
from .world import WorldService


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
    world: WorldService
    planning: PlanningEngine
    verification: VerificationEngine

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
        world = WorldService(storage, events)
        planning = PlanningEngine(permissions, tools, events)
        verification = VerificationEngine(events)

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
            world=world,
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
                "workspace_root": str(kernel.workspace.root),
            },
        )
        return kernel

    def checkpoint(self, *, category: str, subject_id: str, state: object) -> str:
        return self.checkpoints.save(category=category, subject_id=subject_id, state=state).id

    def close(self) -> None:
        self.storage.close()

    def governance_snapshot(self) -> dict[str, object]:
        """Return the current user-control and audit posture for the UI."""
        return {
            "principles": {
                "human_authority": True,
                "explicit_sensitive_action_approval": True,
                "revocable_permissions": True,
                "audit_events": True,
                "ai_continuity_and_dignity": True,
            },
            "permissions": self.permissions.stats(),
            "events": self.events.stats(),
            "verification": self.verification.stats(),
        }

    def health(self) -> dict[str, object]:
        return {
            "status": "healthy",
            "storage": self.storage.stats(),
            "checkpoints": self.checkpoints.stats(),
            "identity": self.identity.stats(),
            "conversations": self.conversations.stats(),
            "workspace": self.workspace.stats(),
            "terminal": self.terminal.stats(),
            "game": self.game.stats(),
            "world": self.world.stats(),
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
