"""Typed event bus, subscriptions, replay, and audit history for NeoGen."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Callable, Iterable
from uuid import uuid4


class EventBusError(RuntimeError):
    """Base error for event operations."""


class EventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    type: str
    source: str
    severity: EventSeverity
    payload: dict[str, Any]
    timestamp: datetime
    correlation_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryFailure:
    event_id: str
    subscriber_id: str
    error: str
    timestamp: datetime


EventHandler = Callable[[Event], None]


class EventBus:
    """Thread-safe synchronous event bus with wildcard subscriptions and replay."""

    def __init__(self, *, history_limit: int = 10_000) -> None:
        if history_limit <= 0:
            raise EventBusError("history_limit must be positive")
        self._history: deque[Event] = deque(maxlen=history_limit)
        self._subscribers: dict[str, dict[str, EventHandler]] = defaultdict(dict)
        self._failures: list[DeliveryFailure] = []
        self._lock = RLock()

    def subscribe(self, event_type: str, handler: EventHandler, *, subscriber_id: str | None = None) -> str:
        normalized_type = self._required(event_type, "event_type")
        identifier = subscriber_id or f"subscriber:{uuid4()}"
        with self._lock:
            if identifier in self._subscribers[normalized_type]:
                raise EventBusError(f"Subscriber already registered for {normalized_type}: {identifier}")
            self._subscribers[normalized_type][identifier] = handler
        return identifier

    def unsubscribe(self, event_type: str, subscriber_id: str) -> bool:
        with self._lock:
            subscribers = self._subscribers.get(event_type)
            if not subscribers or subscriber_id not in subscribers:
                return False
            del subscribers[subscriber_id]
            if not subscribers:
                self._subscribers.pop(event_type, None)
            return True

    def publish(
        self,
        event_type: str,
        *,
        source: str,
        payload: dict[str, Any] | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        correlation_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> Event:
        event = Event(
            id=f"event:{uuid4()}",
            type=self._required(event_type, "event_type"),
            source=self._required(source, "source"),
            severity=severity,
            payload=dict(payload or {}),
            timestamp=datetime.now(timezone.utc),
            correlation_id=self._optional(correlation_id),
            user_id=self._optional(user_id),
            agent_id=self._optional(agent_id),
        )
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscribers.get(event.type, {}).items())
            handlers.extend(self._subscribers.get("*", {}).items())

        for subscriber_id, handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # subscriber isolation boundary
                with self._lock:
                    self._failures.append(
                        DeliveryFailure(
                            event_id=event.id,
                            subscriber_id=subscriber_id,
                            error=f"{type(exc).__name__}: {exc}",
                            timestamp=datetime.now(timezone.utc),
                        )
                    )
        return event

    def replay(
        self,
        *,
        event_types: Iterable[str] = (),
        source: str | None = None,
        correlation_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        minimum_severity: EventSeverity | None = None,
        limit: int = 100,
    ) -> tuple[Event, ...]:
        if limit <= 0:
            raise EventBusError("limit must be positive")
        required_types = frozenset(value.strip() for value in event_types if value.strip())
        severity_order = {
            EventSeverity.DEBUG: 0,
            EventSeverity.INFO: 1,
            EventSeverity.WARNING: 2,
            EventSeverity.ERROR: 3,
            EventSeverity.CRITICAL: 4,
        }
        with self._lock:
            events = list(self._history)
        matches = [
            event
            for event in events
            if (not required_types or event.type in required_types)
            and (source is None or event.source == source)
            and (correlation_id is None or event.correlation_id == correlation_id)
            and (user_id is None or event.user_id == user_id)
            and (agent_id is None or event.agent_id == agent_id)
            and (
                minimum_severity is None
                or severity_order[event.severity] >= severity_order[minimum_severity]
            )
        ]
        return tuple(matches[-limit:])

    def failures(self, *, limit: int = 100) -> tuple[DeliveryFailure, ...]:
        if limit <= 0:
            raise EventBusError("limit must be positive")
        with self._lock:
            return tuple(self._failures[-limit:])

    def clear_failures(self) -> int:
        with self._lock:
            count = len(self._failures)
            self._failures.clear()
            return count

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "events": len(self._history),
                "event_types": len({event.type for event in self._history}),
                "subscriptions": sum(len(items) for items in self._subscribers.values()),
                "delivery_failures": len(self._failures),
            }

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise EventBusError(f"{field} is required")
        return cleaned

    @staticmethod
    def _optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
