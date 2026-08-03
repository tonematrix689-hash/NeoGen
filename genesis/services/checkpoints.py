"""Durable checkpoint persistence for NeoGen runtime state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from .events import EventBus
from .storage import SQLiteStore


class CheckpointError(RuntimeError):
    """Raised when checkpoint state cannot be stored or restored."""


@dataclass(frozen=True, slots=True)
class Checkpoint:
    id: str
    category: str
    subject_id: str
    sequence: int
    state: dict[str, Any]
    created_at: datetime


class CheckpointManager:
    """Store restart-safe snapshots for plans, workflows, agents, and reports."""

    namespace = "runtime.checkpoints"

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()

    def save(
        self,
        *,
        category: str,
        subject_id: str,
        state: Any,
        checkpoint_id: str | None = None,
    ) -> Checkpoint:
        category = self._required(category, "category")
        subject_id = self._required(subject_id, "subject_id")
        identifier = checkpoint_id or f"checkpoint:{uuid4()}"
        sequence = 1
        try:
            existing = self._store.get(self.namespace, identifier)
            sequence = int(existing.value["sequence"]) + 1
        except Exception:
            pass

        created_at = datetime.now(timezone.utc)
        payload = {
            "id": identifier,
            "category": category,
            "subject_id": subject_id,
            "sequence": sequence,
            "state": self._serialize(state),
            "created_at": created_at.isoformat(),
        }
        self._store.put(self.namespace, identifier, payload)
        checkpoint = Checkpoint(
            id=identifier,
            category=category,
            subject_id=subject_id,
            sequence=sequence,
            state=dict(payload["state"]),
            created_at=created_at,
        )
        self._events.publish(
            "CheckpointSaved",
            source="neogen.checkpoints",
            payload={
                "checkpoint_id": identifier,
                "category": category,
                "subject_id": subject_id,
                "sequence": sequence,
            },
        )
        return checkpoint

    def load(self, checkpoint_id: str) -> Checkpoint:
        record = self._store.get(self.namespace, checkpoint_id)
        payload = record.value
        return Checkpoint(
            id=str(payload["id"]),
            category=str(payload["category"]),
            subject_id=str(payload["subject_id"]),
            sequence=int(payload["sequence"]),
            state=dict(payload["state"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )

    def latest(self, *, category: str, subject_id: str) -> Checkpoint | None:
        matches = [
            self.load(record.key)
            for record in self._store.list(self.namespace)
            if record.value.get("category") == category
            and record.value.get("subject_id") == subject_id
        ]
        return max(matches, key=lambda item: (item.sequence, item.created_at)) if matches else None

    def stats(self) -> dict[str, int]:
        checkpoints = [self.load(record.key) for record in self._store.list(self.namespace)]
        return {
            "total": len(checkpoints),
            "categories": len({item.category for item in checkpoints}),
            "subjects": len({item.subject_id for item in checkpoints}),
        }

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        if is_dataclass(value):
            return cls._serialize(asdict(value))
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._serialize(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise CheckpointError(f"Unsupported checkpoint type: {type(value).__name__}")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise CheckpointError(f"{field} is required")
        return cleaned
