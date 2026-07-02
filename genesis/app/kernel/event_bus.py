"""Asynchronous event bus for kernel and service communication."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import inspect
import logging
from typing import Any
from uuid import uuid4


EventHandler = Callable[["Event"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class Event:
    """A typed runtime event emitted by the kernel or a service."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "kernel"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """In-process asynchronous publish/subscribe event bus."""

    def __init__(self, *, history_limit: int = 500, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("genesis.kernel.event_bus")
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: deque[Event] = deque(maxlen=max(0, history_limit))
        self._lock = asyncio.Lock()
        self._closed = False

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register a handler for a specific event name or '*' wildcard."""

        if self._closed:
            raise RuntimeError("Cannot subscribe to a closed event bus.")
        self._handlers[event_name].append(handler)
        self._logger.debug("Registered event handler", extra={"event_name": event_name})

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Remove a previously registered event handler."""

        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event to matching handlers."""

        if self._closed:
            raise RuntimeError(f"Cannot publish event {event.name!r}; event bus is closed.")
        async with self._lock:
            self._history.append(event)
            handlers = [*self._handlers.get(event.name, []), *self._handlers.get("*", [])]
        if not handlers:
            self._logger.debug("Event published without handlers", extra={"event_name": event.name})
            return
        await asyncio.gather(*(self._invoke(handler, event) for handler in handlers))

    async def _invoke(self, handler: EventHandler, event: Event) -> None:
        try:
            result = handler(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self._logger.exception("Event handler failed for %s", event.name)
            raise

    def history(self) -> tuple[Event, ...]:
        """Return recent events retained for diagnostics."""

        return tuple(self._history)

    async def close(self) -> None:
        """Close the event bus and clear handlers."""

        async with self._lock:
            self._closed = True
            self._handlers.clear()
