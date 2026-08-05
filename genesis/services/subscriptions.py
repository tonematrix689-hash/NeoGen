"""Provider-neutral subscription plans and persistent user entitlements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .events import EventBus
from .storage import SQLiteStore, StorageError


class SubscriptionError(RuntimeError):
    """Raised when a subscription request or entitlement is invalid."""


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    level: int | None
    audience: str
    summary: str
    abilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Subscription:
    user_id: str
    plan_id: str
    state: str
    provider: str
    requested_at: datetime
    activated_at: datetime | None


_LEVEL_UNLOCKS = (
    ("neo_chat", "conversation_memory"),
    ("file_attachments", "neo_canvas"),
    ("image_creation", "video_creation", "vision_and_ocr"),
    ("voice_suite",),
    ("workspace_read", "monaco_editor"),
    ("workspace_write", "governed_terminal"),
    ("governed_git", "verification_runs", "static_publish"),
    ("training_lab", "knowledge_library"),
    ("agent_council", "multi_agent_analysis"),
    ("afterlife_forge", "full_individual_suite"),
)

_LEVEL_NAMES = (
    "Spark",
    "Signal",
    "Prism",
    "Resonance",
    "Studio",
    "Operator",
    "Builder",
    "Scholar",
    "Council",
    "Genesis",
)

_LEVEL_SUMMARIES = (
    "Neo chat and persistent conversation memory.",
    "Attach files and turn outcomes into an editable Canvas.",
    "Create images and understand visual source material.",
    "Use speech, transcription, and voice transformation.",
    "Read projects in the Monaco-powered AI Workspace.",
    "Make approval-gated file changes and run terminal tasks.",
    "Use governed Git operations and verification workflows.",
    "Curate attributed knowledge in the Training Lab.",
    "Run the ten-specialist Agent Council and synthesis lead.",
    "Unlock the complete individual suite and Afterlife Forge.",
)


def _plans() -> tuple[Plan, ...]:
    cumulative: list[str] = []
    levels: list[Plan] = []
    for index, (name, summary, unlocks) in enumerate(
        zip(_LEVEL_NAMES, _LEVEL_SUMMARIES, _LEVEL_UNLOCKS, strict=True), start=1
    ):
        cumulative.extend(unlocks)
        levels.append(
            Plan(
                id=f"level-{index}",
                name=name,
                level=index,
                audience="individual",
                summary=summary,
                abilities=tuple(cumulative),
            )
        )

    individual = list(levels[-1].abilities)
    admin_abilities = individual + [
        "team_workspaces",
        "shared_admin",
        "audit_exports",
        "subscription_admin",
        "user_administration",
        "policy_configuration",
        "connector_governance",
    ]
    enterprise_abilities = individual + [
        "team_workspaces",
        "shared_admin",
        "audit_exports",
        "sso_and_scim",
        "private_deployment",
        "compliance_controls",
        "priority_governance",
    ]
    owner_abilities = list(dict.fromkeys(
        admin_abilities
        + enterprise_abilities
        + [
            "platform_ownership",
            "billing_configuration",
            "deployment_authority",
            "emergency_recovery",
        ]
    ))
    return tuple(levels) + (
        Plan(
            id="admin",
            name="Admin",
            level=11,
            audience="administration",
            summary="User, subscription, connector, and policy administration.",
            abilities=tuple(admin_abilities),
        ),
        Plan(
            id="owner",
            name="Owner",
            level=12,
            audience="owner",
            summary="Complete platform authority, billing configuration, and recovery control.",
            abilities=tuple(owner_abilities),
        ),
        Plan(
            id="business",
            name="Business",
            level=None,
            audience="organization",
            summary="Shared workspaces, team administration, and auditable operations.",
            abilities=tuple(individual + ["team_workspaces", "shared_admin", "audit_exports"]),
        ),
        Plan(
            id="enterprise",
            name="Enterprise",
            level=None,
            audience="organization",
            summary="Private deployment, enterprise identity, and policy controls.",
            abilities=tuple(enterprise_abilities),
        ),
    )


class SubscriptionService:
    """Own the catalogue and entitlement state without processing payment data."""

    subscription_namespace = "subscriptions.active"
    request_namespace = "subscriptions.requests"

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()
        self._plans = {plan.id: plan for plan in _plans()}

    def catalog(self) -> tuple[Plan, ...]:
        return tuple(self._plans.values())

    def plan(self, plan_id: str) -> Plan:
        try:
            return self._plans[plan_id.strip().lower()]
        except (KeyError, AttributeError) as exc:
            raise SubscriptionError(f"Unknown subscription plan: {plan_id}") from exc

    def ensure(self, user_id: str) -> Subscription:
        try:
            return self._from_record(self._store.get(self.subscription_namespace, user_id).value)
        except StorageError:
            return self.activate(user_id, "level-1", provider="neogen-free")

    def current(self, user_id: str) -> dict[str, Any]:
        subscription = self.ensure(user_id)
        return {
            "subscription": subscription,
            "plan": self.plan(subscription.plan_id),
        }

    def request(self, user_id: str, plan_id: str) -> dict[str, Any]:
        plan = self.plan(plan_id)
        if plan.id in {"admin", "owner"}:
            raise SubscriptionError(f"{plan.name} is role-assigned and cannot be self-requested")
        if plan.id == "level-1":
            return {
                "subscription": self.activate(user_id, plan.id, provider="neogen-free"),
                "plan": plan,
                "checkout_required": False,
            }
        requested_at = datetime.now(timezone.utc)
        record = {
            "user_id": user_id,
            "plan_id": plan.id,
            "state": "pending_provider",
            "provider": "unconfigured",
            "requested_at": requested_at.isoformat(),
            "activated_at": None,
        }
        self._store.put(self.request_namespace, user_id, record)
        self._events.publish(
            "SubscriptionRequested",
            source="neogen.subscriptions",
            payload={"user_id": user_id, "plan_id": plan.id},
            user_id=user_id,
        )
        return {
            "subscription": self._from_record(record),
            "plan": plan,
            "checkout_required": True,
        }

    def activate(self, user_id: str, plan_id: str, *, provider: str) -> Subscription:
        plan = self.plan(plan_id)
        timestamp = datetime.now(timezone.utc)
        record = {
            "user_id": user_id,
            "plan_id": plan.id,
            "state": "active",
            "provider": provider.strip() or "manual",
            "requested_at": timestamp.isoformat(),
            "activated_at": timestamp.isoformat(),
        }
        self._store.put(self.subscription_namespace, user_id, record)
        self._events.publish(
            "SubscriptionActivated",
            source="neogen.subscriptions",
            payload={"user_id": user_id, "plan_id": plan.id, "provider": record["provider"]},
            user_id=user_id,
        )
        return self._from_record(record)

    def has_ability(self, user_id: str, ability: str) -> bool:
        current = self.ensure(user_id)
        return ability.strip().lower() in self.plan(current.plan_id).abilities

    def stats(self) -> dict[str, int]:
        return {
            "plans": len(self._plans),
            "active": len(self._store.list(self.subscription_namespace)),
            "pending": len(self._store.list(self.request_namespace)),
        }

    @staticmethod
    def _from_record(record: dict[str, Any]) -> Subscription:
        activated = record.get("activated_at")
        return Subscription(
            user_id=str(record["user_id"]),
            plan_id=str(record["plan_id"]),
            state=str(record["state"]),
            provider=str(record["provider"]),
            requested_at=datetime.fromisoformat(str(record["requested_at"])),
            activated_at=datetime.fromisoformat(str(activated)) if activated else None,
        )
