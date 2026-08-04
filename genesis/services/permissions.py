"""Permission and approval management for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from uuid import uuid4


class PermissionError(RuntimeError):
    """Base error for permission operations."""


class PermissionScope(StrEnum):
    READ_MEMORY = "memory.read"
    WRITE_MEMORY = "memory.write"
    READ_FILES = "files.read"
    WRITE_FILES = "files.write"
    RUN_TERMINAL = "terminal.run"
    USE_NETWORK = "network.use"
    MANAGE_PLUGINS = "plugins.manage"
    USE_MODELS = "models.use"
    SPEND_FUNDS = "funds.spend"
    TRADE_ASSETS = "assets.trade"
    MINT_ASSETS = "assets.mint"
    DEPLOY = "deploy.execute"
    ADMIN = "admin"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class Grant:
    id: str
    subject_id: str
    scope: PermissionScope
    resource: str
    granted_by: str
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    subject_id: str
    scope: PermissionScope
    resource: str
    reason: str
    risk: float
    status: ApprovalStatus
    requested_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str
    request_id: str | None = None


class PermissionManager:
    """Thread-safe grants, approvals, revocation, and policy evaluation."""

    HIGH_RISK_SCOPES = frozenset(
        {
            PermissionScope.SPEND_FUNDS,
            PermissionScope.TRADE_ASSETS,
            PermissionScope.MINT_ASSETS,
            PermissionScope.DEPLOY,
            PermissionScope.ADMIN,
        }
    )

    def __init__(self) -> None:
        self._grants: dict[str, Grant] = {}
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = RLock()

    def grant(
        self,
        *,
        subject_id: str,
        scope: PermissionScope,
        resource: str = "*",
        granted_by: str,
    ) -> Grant:
        grant = Grant(
            id=f"grant:{uuid4()}",
            subject_id=self._required(subject_id, "subject_id"),
            scope=scope,
            resource=self._required(resource, "resource"),
            granted_by=self._required(granted_by, "granted_by"),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._grants[grant.id] = grant
        return grant

    def revoke(self, grant_id: str) -> Grant:
        with self._lock:
            try:
                grant = self._grants[grant_id]
            except KeyError as exc:
                raise PermissionError(f"Unknown grant: {grant_id}") from exc
            if not grant.active:
                return grant
            revoked = replace(grant, revoked_at=datetime.now(timezone.utc))
            self._grants[grant_id] = revoked
            return revoked

    def request(
        self,
        *,
        subject_id: str,
        scope: PermissionScope,
        resource: str,
        reason: str,
        risk: float = 0.5,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            id=f"approval:{uuid4()}",
            subject_id=self._required(subject_id, "subject_id"),
            scope=scope,
            resource=self._required(resource, "resource"),
            reason=self._required(reason, "reason"),
            risk=self._risk(risk),
            status=ApprovalStatus.PENDING,
            requested_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._requests[request.id] = request
        return request

    def resolve(self, request_id: str, *, approved: bool, resolved_by: str) -> ApprovalRequest:
        with self._lock:
            try:
                request = self._requests[request_id]
            except KeyError as exc:
                raise PermissionError(f"Unknown approval request: {request_id}") from exc
            if request.status is not ApprovalStatus.PENDING:
                raise PermissionError("Approval request has already been resolved")
            updated = replace(
                request,
                status=ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED,
                resolved_at=datetime.now(timezone.utc),
                resolved_by=self._required(resolved_by, "resolved_by"),
            )
            self._requests[request_id] = updated
            if approved:
                self.grant(
                    subject_id=updated.subject_id,
                    scope=updated.scope,
                    resource=updated.resource,
                    granted_by=updated.resolved_by or "unknown",
                )
            return updated

    def evaluate(
        self,
        *,
        subject_id: str,
        scope: PermissionScope,
        resource: str,
        reason: str = "Requested action",
        risk: float = 0.5,
        auto_request: bool = False,
    ) -> PermissionDecision:
        if self.has_permission(subject_id=subject_id, scope=scope, resource=resource):
            return PermissionDecision(True, False, "Active grant found")

        requires_approval = scope in self.HIGH_RISK_SCOPES or risk >= 0.7
        if not requires_approval:
            return PermissionDecision(False, False, "Permission not granted")

        if not auto_request:
            return PermissionDecision(False, True, "Explicit approval required")

        request = self.request(
            subject_id=subject_id,
            scope=scope,
            resource=resource,
            reason=reason,
            risk=risk,
        )
        return PermissionDecision(False, True, "Approval request created", request.id)

    def check(
        self,
        *,
        subject_id: str,
        scope: PermissionScope,
        resource: str,
    ) -> PermissionDecision:
        """Compatibility alias for callers that only need a permission decision."""
        return self.evaluate(
            subject_id=subject_id,
            scope=scope,
            resource=resource,
            auto_request=False,
        )

    def has_permission(self, *, subject_id: str, scope: PermissionScope, resource: str) -> bool:
        with self._lock:
            for grant in self._grants.values():
                if not grant.active or grant.subject_id != subject_id:
                    continue
                if grant.scope not in {scope, PermissionScope.ADMIN}:
                    continue
                if grant.resource in {"*", resource}:
                    return True
            return False

    def active_grants(self, subject_id: str | None = None) -> tuple[Grant, ...]:
        with self._lock:
            return tuple(
                grant
                for grant in self._grants.values()
                if grant.active and (subject_id is None or grant.subject_id == subject_id)
            )

    def pending_requests(self, subject_id: str | None = None) -> tuple[ApprovalRequest, ...]:
        with self._lock:
            return tuple(
                request
                for request in self._requests.values()
                if request.status is ApprovalStatus.PENDING
                and (subject_id is None or request.subject_id == subject_id)
            )

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_grants": sum(1 for grant in self._grants.values() if grant.active),
                "revoked_grants": sum(1 for grant in self._grants.values() if not grant.active),
                "pending_approvals": sum(
                    1 for request in self._requests.values() if request.status is ApprovalStatus.PENDING
                ),
                "approved": sum(
                    1 for request in self._requests.values() if request.status is ApprovalStatus.APPROVED
                ),
                "denied": sum(
                    1 for request in self._requests.values() if request.status is ApprovalStatus.DENIED
                ),
            }

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise PermissionError(f"{field} is required")
        return cleaned

    @staticmethod
    def _risk(value: float) -> float:
        risk = float(value)
        if not 0.0 <= risk <= 1.0:
            raise PermissionError("risk must be between 0 and 1")
        return risk
