"""Coordinated code improvement with exact approvals, tests, learning, and rollback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from genesis.app.coding import CodeChange, CodeProposal, CodeWorkspaceTool
from genesis.app.learning import LearningService
from genesis.app.memory import MemoryService
from genesis.app.security import ApprovalRequest, ApprovalState, PermissionEngine
from genesis.app.tools import TerminalResult, TerminalTool


class ImprovementState(StrEnum):
    PREPARED = "prepared"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class VerificationStep:
    arguments: tuple[str, ...]
    approval: ApprovalRequest


@dataclass(frozen=True, slots=True)
class ImprovementPlan:
    id: str
    project_id: str
    goal: str
    strategy: str
    source_urls: tuple[str, ...]
    changes: tuple[CodeChange, ...]
    code_proposal: CodeProposal
    verification_steps: tuple[VerificationStep, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class ImprovementResult:
    plan_id: str
    state: ImprovementState
    checkpoint_id: str | None
    verification_results: tuple[TerminalResult, ...]
    error: str | None = None


class SelfImprovementService:
    """Runs only fully approved improvement plans and automatically rolls back failed checks."""

    def __init__(
        self,
        permissions: PermissionEngine,
        coding: CodeWorkspaceTool,
        terminal: TerminalTool,
        memory: MemoryService,
        learning: LearningService,
        *,
        max_verification_steps: int = 8,
    ) -> None:
        self.permissions = permissions
        self.coding = coding
        self.terminal = terminal
        self.memory = memory
        self.learning = learning
        self.max_verification_steps = max_verification_steps
        self._states: dict[str, ImprovementState] = {}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def prepare(
        self,
        project_id: str,
        goal: str,
        changes: tuple[CodeChange, ...],
        verification_commands: tuple[tuple[str, ...], ...],
        *,
        strategy: str = "neogen",
        source_urls: tuple[str, ...] = (),
    ) -> ImprovementPlan:
        goal = goal.strip()
        if not goal or len(goal) > 1_000:
            raise ValueError("goal must contain between 1 and 1000 characters")
        if not strategy.strip() or len(strategy) > 200:
            raise ValueError("strategy must contain between 1 and 200 characters")
        if not verification_commands:
            raise ValueError("At least one verification command is required.")
        if len(verification_commands) > self.max_verification_steps:
            raise ValueError("Improvement plan exceeds the verification-step limit.")
        if len(source_urls) > 20:
            raise ValueError("Improvement plan exceeds the source URL limit.")
        for source_url in source_urls:
            if not source_url.startswith("https://") or len(source_url) > 2_000:
                raise ValueError("Research sources must be bounded HTTPS URLs.")

        code_proposal = self.coding.propose(project_id, changes)
        steps = tuple(
            VerificationStep(arguments, self.terminal.request_run(project_id, arguments))
            for arguments in verification_commands
        )
        plan = ImprovementPlan(
            str(uuid4()),
            project_id,
            goal,
            strategy.strip(),
            source_urls,
            changes,
            code_proposal,
            steps,
            datetime.now(UTC).isoformat(),
        )
        self._states[plan.id] = ImprovementState.PREPARED
        self.memory.remember(
            project_id,
            f"Prepared improvement {plan.id}: {goal}",
            category="self_improvement",
        )
        return plan

    def state(self, plan_id: str) -> ImprovementState:
        try:
            return self._states[plan_id]
        except KeyError as exc:
            raise KeyError(f"Unknown improvement plan: {plan_id}") from exc

    async def execute(self, plan: ImprovementPlan) -> ImprovementResult:
        if self.state(plan.id) is not ImprovementState.PREPARED:
            raise RuntimeError(f"Improvement plan is already {self.state(plan.id)}.")
        approvals = (plan.code_proposal.approval,) + tuple(
            step.approval for step in plan.verification_steps
        )
        if any(self.permissions.require(item.id).state is not ApprovalState.APPROVED for item in approvals):
            raise PermissionError("Every code and verification action must be approved before execution.")

        self._states[plan.id] = ImprovementState.RUNNING
        checkpoint_id: str | None = None
        results: list[TerminalResult] = []
        try:
            checkpoint_id = self.coding.apply(
                plan.project_id,
                plan.changes,
                plan.code_proposal.approval.id,
            )
            for step in plan.verification_steps:
                result = await self.terminal.run(
                    plan.project_id,
                    step.arguments,
                    step.approval.id,
                )
                results.append(result)
                if result.exit_code != 0:
                    raise RuntimeError(
                        f"Verification command exited with code {result.exit_code}: "
                        f"{' '.join(step.arguments)}"
                    )
        except Exception as exc:
            recovery_error: Exception | None = None
            if checkpoint_id is not None:
                try:
                    self.coding.recover_failed_change(plan.project_id, checkpoint_id)
                except Exception as rollback_exc:
                    recovery_error = rollback_exc
            result_state = (
                ImprovementState.FAILED
                if recovery_error is not None
                else ImprovementState.ROLLED_BACK
            )
            self._states[plan.id] = result_state
            self.learning.record_outcome(
                plan.project_id,
                "self_improvement",
                plan.strategy,
                0.0,
                source="verification",
            )
            self.memory.remember(
                plan.project_id,
                (
                    f"Recovery conflict for improvement {plan.id}."
                    if recovery_error is not None
                    else f"Rolled back improvement {plan.id} after verification failure."
                ),
                category="self_improvement",
            )
            error = str(exc)
            if recovery_error is not None:
                error = f"{error}; recovery conflict: {recovery_error}"
            return ImprovementResult(
                plan.id,
                result_state,
                checkpoint_id,
                tuple(results),
                error,
            )

        self._states[plan.id] = ImprovementState.SUCCEEDED
        self.learning.record_outcome(
            plan.project_id,
            "self_improvement",
            plan.strategy,
            1.0,
            source="verification",
        )
        self.memory.remember(
            plan.project_id,
            f"Completed improvement {plan.id}; recovery checkpoint {checkpoint_id}.",
            category="self_improvement",
        )
        return ImprovementResult(
            plan.id,
            ImprovementState.SUCCEEDED,
            checkpoint_id,
            tuple(results),
        )
