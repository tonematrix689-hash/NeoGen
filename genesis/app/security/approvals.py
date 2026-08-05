"""Single-use approval requests for guarded tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from threading import RLock
from uuid import uuid4


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    project_id: str
    capability: str
    summary: str
    action_digest: str
    state: ApprovalState
    created_at: str


class PermissionEngine:
    """Tracks explicit, inspectable and single-use user approvals."""

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = RLock()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def request(self, project_id: str, capability: str, summary: str, *, action: str) -> ApprovalRequest:
        request = ApprovalRequest(
            str(uuid4()),
            project_id,
            capability,
            summary,
            self.digest(action),
            ApprovalState.PENDING,
            datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._requests[request.id] = request
        return request

    def decide(self, request_id: str, *, approved: bool) -> ApprovalRequest:
        with self._lock:
            current = self.require(request_id)
            if current.state is not ApprovalState.PENDING:
                raise ValueError(f"Approval request is already {current.state}.")
            updated = self._replace(current, ApprovalState.APPROVED if approved else ApprovalState.DENIED)
            self._requests[request_id] = updated
            return updated

    def consume(self, request_id: str, project_id: str, capability: str, *, action: str) -> ApprovalRequest:
        with self._lock:
            current = self.require(request_id)
            if current.project_id != project_id or current.capability != capability:
                raise PermissionError("Approval does not match this project and capability.")
            if current.action_digest != self.digest(action):
                raise PermissionError("Approval does not match the exact requested action.")
            if current.state is not ApprovalState.APPROVED:
                raise PermissionError(f"Approval is not executable: {current.state}.")
            consumed = self._replace(current, ApprovalState.CONSUMED)
            self._requests[request_id] = consumed
            return consumed

    def require(self, request_id: str) -> ApprovalRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise KeyError(f"Unknown approval request: {request_id}")
        return request

    def pending(self, project_id: str) -> tuple[ApprovalRequest, ...]:
        with self._lock:
            return tuple(
                request
                for request in self._requests.values()
                if request.project_id == project_id and request.state is ApprovalState.PENDING
            )

    @staticmethod
    def _replace(request: ApprovalRequest, state: ApprovalState) -> ApprovalRequest:
        return ApprovalRequest(
            request.id,
            request.project_id,
            request.capability,
            request.summary,
            request.action_digest,
            state,
            request.created_at,
        )

    @staticmethod
    def digest(action: str) -> str:
        return sha256(action.encode("utf-8")).hexdigest()
