"""Application-facing façade for the post-login Genesis workspace."""

from __future__ import annotations

from dataclasses import dataclass

from genesis.app.coding import CodeChange, CodeFile, CodeFileSummary, CodeProposal, CodeWorkspaceTool
from genesis.app.improvement import ImprovementPlan, ImprovementResult, SelfImprovementService
from genesis.app.kernel.registry import ServiceRegistry
from genesis.app.learning import LearningService, OutcomeRecord, StrategyScore
from genesis.app.memory import ConversationTurn, MemoryRecord, MemoryService
from genesis.app.research import ResearchResult, WebPage, WebResearchTool
from genesis.app.repository import RepositoryResult, RepositoryService, RepositorySnapshot
from genesis.app.security import ApprovalRequest, PermissionEngine
from genesis.app.tools import TerminalResult, TerminalTool, WorkspaceFileTool


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    project_id: str
    capabilities: tuple[str, ...]
    pending_approvals: tuple[ApprovalRequest, ...]


class WorkspaceService:
    """Connects UI requests to memory and guarded capabilities."""

    def __init__(
        self,
        memory: MemoryService,
        permissions: PermissionEngine,
        files: WorkspaceFileTool,
        terminal: TerminalTool,
        coding: CodeWorkspaceTool,
        research: WebResearchTool,
        repository: RepositoryService,
        learning: LearningService,
        improvement: SelfImprovementService,
        registry: ServiceRegistry,
    ) -> None:
        self.memory = memory
        self.permissions = permissions
        self.files = files
        self.terminal = terminal
        self.coding = coding
        self.research = research
        self.repository = repository
        self.learning = learning
        self.improvement = improvement
        self.registry = registry

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def snapshot(self, project_id: str) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            project_id,
            tuple(entry.name for entry in self.registry.list()),
            self.permissions.pending(project_id),
        )

    def remember(self, project_id: str, content: str, *, category: str = "general") -> MemoryRecord:
        return self.memory.remember(project_id, content, category=category)

    def add_message(
        self, project_id: str, conversation_id: str, role: str, content: str
    ) -> ConversationTurn:
        return self.memory.add_turn(project_id, conversation_id, role, content)

    def conversation(self, project_id: str, conversation_id: str) -> tuple[ConversationTurn, ...]:
        return self.memory.conversation(project_id, conversation_id)

    def request_file_write(self, project_id: str, relative_path: str, content: str) -> ApprovalRequest:
        return self.files.request_write(project_id, relative_path, content)

    def write_file(
        self, project_id: str, relative_path: str, content: str, approval_id: str
    ) -> str:
        return str(self.files.write_text(project_id, relative_path, content, approval_id))

    def request_terminal(self, project_id: str, arguments: tuple[str, ...]) -> ApprovalRequest:
        return self.terminal.request_run(project_id, arguments)

    async def run_terminal(
        self, project_id: str, arguments: tuple[str, ...], approval_id: str
    ) -> TerminalResult:
        return await self.terminal.run(project_id, arguments, approval_id)

    def code_inventory(self, *, limit: int = 500) -> tuple[CodeFileSummary, ...]:
        return self.coding.inventory(limit=limit)

    def read_code(self, relative_path: str) -> CodeFile:
        return self.coding.read(relative_path)

    def new_code_file(self, relative_path: str) -> CodeFile:
        return self.coding.missing_file(relative_path)

    def propose_code_changes(
        self, project_id: str, changes: tuple[CodeChange, ...]
    ) -> CodeProposal:
        return self.coding.propose(project_id, changes)

    def apply_code_changes(
        self, project_id: str, changes: tuple[CodeChange, ...], approval_id: str
    ) -> str:
        return self.coding.apply(project_id, changes, approval_id)

    def request_code_restore(self, project_id: str, checkpoint_id: str) -> ApprovalRequest:
        return self.coding.request_restore(project_id, checkpoint_id)

    def restore_code(self, project_id: str, checkpoint_id: str, approval_id: str) -> None:
        self.coding.restore(project_id, checkpoint_id, approval_id)

    def request_web_search(
        self, project_id: str, query: str, *, max_results: int = 8
    ) -> ApprovalRequest:
        return self.research.request_search(project_id, query, max_results=max_results)

    async def web_search(
        self,
        project_id: str,
        query: str,
        approval_id: str,
        *,
        max_results: int = 8,
    ) -> tuple[ResearchResult, ...]:
        return await self.research.search(
            project_id, query, approval_id, max_results=max_results
        )

    def request_web_read(self, project_id: str, url: str) -> ApprovalRequest:
        return self.research.request_read(project_id, url)

    async def web_read(self, project_id: str, url: str, approval_id: str) -> WebPage:
        return await self.research.read(project_id, url, approval_id)

    def repository_snapshot(self) -> RepositorySnapshot:
        return self.repository.snapshot()

    def repository_status(self) -> str:
        return self.repository.status()

    def repository_diff(self, *paths: str) -> str:
        return self.repository.diff(*paths)

    def repository_log(self, *, limit: int = 25) -> str:
        return self.repository.log(limit=limit)

    def request_repository(
        self, project_id: str, arguments: tuple[str, ...]
    ) -> ApprovalRequest:
        return self.repository.request(project_id, arguments)

    async def run_repository(
        self,
        project_id: str,
        arguments: tuple[str, ...],
        approval_id: str,
    ) -> RepositoryResult:
        return await self.repository.run(project_id, arguments, approval_id)

    def record_learning_outcome(
        self,
        project_id: str,
        task_kind: str,
        strategy: str,
        reward: float,
        *,
        source: str = "user",
    ) -> OutcomeRecord:
        return self.learning.record_outcome(
            project_id, task_kind, strategy, reward, source=source
        )

    def rank_strategies(
        self,
        project_id: str,
        task_kind: str,
        candidates: tuple[str, ...],
    ) -> tuple[StrategyScore, ...]:
        return self.learning.rank_strategies(project_id, task_kind, candidates)

    def prepare_improvement(
        self,
        project_id: str,
        goal: str,
        changes: tuple[CodeChange, ...],
        verification_commands: tuple[tuple[str, ...], ...],
        *,
        strategy: str = "neogen",
        source_urls: tuple[str, ...] = (),
    ) -> ImprovementPlan:
        return self.improvement.prepare(
            project_id,
            goal,
            changes,
            verification_commands,
            strategy=strategy,
            source_urls=source_urls,
        )

    async def execute_improvement(self, plan: ImprovementPlan) -> ImprovementResult:
        return await self.improvement.execute(plan)

    def improvement_plan(self, plan_id: str) -> ImprovementPlan:
        return self.improvement.get(plan_id)
