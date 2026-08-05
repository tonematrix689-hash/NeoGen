"""Composition helpers for a complete local Genesis workspace runtime."""

from __future__ import annotations

from genesis.app.coding import CodeWorkspaceTool
from genesis.app.improvement import SelfImprovementService
from genesis.app.kernel import GenesisRuntime, GenesisSettings, ServiceDescriptor
from genesis.app.learning import LearningService
from genesis.app.memory import MemoryService
from genesis.app.research import WebResearchTool
from genesis.app.security import PermissionEngine
from genesis.app.tools import TerminalTool, WorkspaceFileTool
from genesis.app.workspace import WorkspaceService


def create_workspace_runtime(settings: GenesisSettings | None = None) -> GenesisRuntime:
    runtime = GenesisRuntime(settings)
    data_dir = runtime.settings.data_dir
    workspace_root = runtime.settings.workspace_dir or data_dir / "workspace"
    permissions = PermissionEngine()
    memory = MemoryService(data_dir / "memory" / "genesis.db")
    learning = LearningService(data_dir / "learning" / "outcomes.db")
    files = WorkspaceFileTool(workspace_root, permissions)
    terminal = TerminalTool(workspace_root, permissions)
    coding = CodeWorkspaceTool(workspace_root, data_dir / "checkpoints", permissions)
    research = WebResearchTool(permissions)
    improvement = SelfImprovementService(
        permissions, coding, terminal, memory, learning
    )
    workspace = WorkspaceService(
        memory,
        permissions,
        files,
        terminal,
        coding,
        research,
        learning,
        improvement,
        runtime.registry,
    )

    descriptors = (
        ServiceDescriptor("permissions", "0.1.0", "Explicit approval engine.", permissions, priority=10),
        ServiceDescriptor("memory", "0.1.0", "Persistent workspace memory.", memory, priority=20),
        ServiceDescriptor(
            "learning",
            "0.1.0",
            "Project-scoped adaptive strategy learning.",
            learning,
            priority=20,
            kind="capability",
        ),
        ServiceDescriptor(
            "files", "0.1.0", "Workspace-scoped file operations.", files, priority=30, dependencies=("permissions",)
        ),
        ServiceDescriptor(
            "terminal", "0.1.0", "Approval-gated terminal execution.", terminal, priority=30, dependencies=("permissions",)
        ),
        ServiceDescriptor(
            "coding",
            "0.1.0",
            "Recoverable source inspection and editing.",
            coding,
            priority=30,
            dependencies=("permissions",),
            kind="capability",
        ),
        ServiceDescriptor(
            "research",
            "0.1.0",
            "Consent-gated public web research.",
            research,
            priority=30,
            dependencies=("permissions",),
            kind="capability",
        ),
        ServiceDescriptor(
            "improvement",
            "0.1.0",
            "Approval-bundled, test-gated code self-improvement.",
            improvement,
            priority=40,
            dependencies=("permissions", "memory", "learning", "coding", "terminal"),
            kind="capability",
        ),
        ServiceDescriptor(
            "workspace",
            "0.1.0",
            "Post-login workspace façade.",
            workspace,
            priority=50,
            dependencies=(
                "memory",
                "permissions",
                "files",
                "terminal",
                "coding",
                "research",
                "learning",
                "improvement",
            ),
        ),
    )
    for descriptor in descriptors:
        runtime.register_service(descriptor)
    return runtime
