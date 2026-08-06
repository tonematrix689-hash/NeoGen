"""Domain models for the Dream Life application layer.

The models deliberately separate observations from interpretations:
- activities record what happened;
- goals describe desired outcomes;
- progress is bounded and explicit;
- rewards are proposals, never automatic financial transfers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class Status(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActivityOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class RiskClass(StrEnum):
    READ_ONLY = "read_only"
    SENSITIVE_READ = "sensitive_read"
    REVERSIBLE_ACTION = "reversible_action"
    PRIVILEGED_ACTION = "privileged_action"
    IRREVERSIBLE_ACTION = "irreversible_action"


@dataclass(frozen=True, slots=True)
class Identity:
    user_id: str
    display_name: str
    values: tuple[str, ...] = ()
    interests: tuple[str, ...] = ()
    preferences: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Aspiration:
    aspiration_id: str
    user_id: str
    title: str
    category: str
    description: str = ""
    importance: float = 0.5
    status: Status = Status.ACTIVE
    target_outcomes: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("aspiration title cannot be empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    aspiration_id: str
    user_id: str
    title: str
    description: str = ""
    status: Status = Status.ACTIVE
    progress: float = 0.0
    next_action: str = ""
    due_at: str | None = None
    evidence_required: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("goal title cannot be empty")
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("goal progress must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Activity:
    activity_id: str
    user_id: str
    activity_type: str
    title: str
    goal_id: str | None = None
    project: str | None = None
    device_id: str | None = None
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    duration_seconds: int | None = None
    outcome: ActivityOutcome = ActivityOutcome.UNKNOWN
    evidence: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class Mission:
    mission_id: str
    user_id: str
    goal_id: str
    title: str
    instructions: tuple[str, ...]
    completion_evidence: tuple[str, ...]
    estimated_minutes: int
    status: Status = Status.PROPOSED
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.estimated_minutes <= 0:
            raise ValueError("estimated_minutes must be positive")


@dataclass(frozen=True, slots=True)
class RewardProposal:
    proposal_id: str
    user_id: str
    source_activity_id: str
    reward_type: str
    amount: int
    rationale: str
    status: Status = Status.PROPOSED
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("reward amount cannot be negative")


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    user_id: str
    capability: str
    parameters_hash: str
    risk_class: RiskClass
    expires_at: str
    single_use: bool = True
    used_at: str | None = None
    created_at: str = field(default_factory=utc_now)

    @staticmethod
    def hash_parameters(parameters: Mapping[str, Any]) -> str:
        canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: Mapping[str, Any]
    occurred_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    screen_view: bool = False
    remote_input: bool = False
    terminal: bool = False
    file_share: bool = False
    clipboard: bool = False
    camera: bool = False
    microphone: bool = False
    security_monitor: bool = False


@dataclass(frozen=True, slots=True)
class Device:
    device_id: str
    name: str
    platform: str
    connection: str
    status: str
    capabilities: DeviceCapabilities
    last_seen_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ShareItem:
    source_path: str
    destination_path: str
    size: int
    sha256: str


class TransportKind(StrEnum):
    AUTO = "auto"
    LOCAL = "local"
    DROPBOX = "dropbox"
    BLUETOOTH = "bluetooth"
    QUICK_SHARE = "quick_share"


@dataclass(frozen=True, slots=True)
class ShareRequest:
    request_id: str
    user_id: str
    source_device_id: str
    destination: str
    items: tuple[ShareItem, ...]
    preferred_transport: TransportKind = TransportKind.AUTO
    require_encryption: bool = True
    require_confirmation: bool = True
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ShareResult:
    request_id: str
    transport: TransportKind
    success: bool
    message: str
    transferred_items: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    completed_at: str = field(default_factory=utc_now)


def to_dict(value: Any) -> dict[str, Any]:
    """Convert a dataclass to JSON-compatible data, including enums."""

    raw = asdict(value)

    def normalize(item: Any) -> Any:
        if isinstance(item, StrEnum):
            return item.value
        if isinstance(item, dict):
            return {key: normalize(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(val) for val in item]
        return item

    return normalize(raw)
