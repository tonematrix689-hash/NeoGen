"""Typed in-memory memory engine for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Iterable
from uuid import uuid4


class MemoryError(RuntimeError):
    """Base error for memory operations."""


class MemoryDomain(StrEnum):
    SESSION = "session"
    USER = "user"
    PROJECT = "project"
    WORKSPACE = "workspace"
    TEAM = "team"
    KNOWLEDGE = "knowledge"
    DOCUMENT = "document"
    CODE = "code"
    COMPANION = "companion"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    domain: MemoryDomain
    owner_id: str
    title: str
    content: str
    tags: frozenset[str]
    importance: float
    confidence: float
    source: str
    relationships: frozenset[str]
    version: int
    created_at: datetime
    updated_at: datetime


class MemoryEngine:
    """Thread-safe memory store with immutable version history."""

    def __init__(self) -> None:
        self._current: dict[str, MemoryRecord] = {}
        self._history: dict[str, list[MemoryRecord]] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        domain: MemoryDomain,
        owner_id: str,
        title: str,
        content: str,
        tags: Iterable[str] = (),
        importance: float = 0.5,
        confidence: float = 1.0,
        source: str = "user",
        relationships: Iterable[str] = (),
    ) -> MemoryRecord:
        owner = self._required(owner_id, "owner_id")
        normalized_title = self._required(title, "title")
        normalized_content = self._required(content, "content")
        now = datetime.now(timezone.utc)
        record = MemoryRecord(
            id=f"memory:{uuid4()}",
            domain=domain,
            owner_id=owner,
            title=normalized_title,
            content=normalized_content,
            tags=self._normalize_set(tags),
            importance=self._score(importance, "importance"),
            confidence=self._score(confidence, "confidence"),
            source=self._required(source, "source"),
            relationships=self._normalize_set(relationships),
            version=1,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._current[record.id] = record
            self._history[record.id] = [record]
        return record

    def get(self, memory_id: str) -> MemoryRecord:
        with self._lock:
            try:
                return self._current[memory_id]
            except KeyError as exc:
                raise MemoryError(f"Unknown memory: {memory_id}") from exc

    def update(
        self,
        memory_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: Iterable[str] | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        source: str | None = None,
        relationships: Iterable[str] | None = None,
    ) -> MemoryRecord:
        with self._lock:
            current = self.get(memory_id)
            updated = replace(
                current,
                title=current.title if title is None else self._required(title, "title"),
                content=current.content if content is None else self._required(content, "content"),
                tags=current.tags if tags is None else self._normalize_set(tags),
                importance=current.importance if importance is None else self._score(importance, "importance"),
                confidence=current.confidence if confidence is None else self._score(confidence, "confidence"),
                source=current.source if source is None else self._required(source, "source"),
                relationships=current.relationships if relationships is None else self._normalize_set(relationships),
                version=current.version + 1,
                updated_at=datetime.now(timezone.utc),
            )
            self._current[memory_id] = updated
            self._history[memory_id].append(updated)
            return updated

    def delete(self, memory_id: str) -> MemoryRecord:
        with self._lock:
            record = self.get(memory_id)
            del self._current[memory_id]
            return record

    def history(self, memory_id: str) -> tuple[MemoryRecord, ...]:
        with self._lock:
            try:
                return tuple(self._history[memory_id])
            except KeyError as exc:
                raise MemoryError(f"Unknown memory: {memory_id}") from exc

    def search(
        self,
        *,
        owner_id: str | None = None,
        domain: MemoryDomain | None = None,
        tags: Iterable[str] = (),
        text: str | None = None,
        minimum_importance: float = 0.0,
        minimum_confidence: float = 0.0,
        limit: int = 50,
    ) -> tuple[MemoryRecord, ...]:
        required_tags = self._normalize_set(tags)
        query = "" if text is None else text.strip().lower()
        min_importance = self._score(minimum_importance, "minimum_importance")
        min_confidence = self._score(minimum_confidence, "minimum_confidence")
        if limit <= 0:
            raise MemoryError("limit must be greater than zero")

        with self._lock:
            records = list(self._current.values())

        matches = [
            record
            for record in records
            if (owner_id is None or record.owner_id == owner_id)
            and (domain is None or record.domain is domain)
            and required_tags.issubset(record.tags)
            and record.importance >= min_importance
            and record.confidence >= min_confidence
            and (
                not query
                or query in record.title.lower()
                or query in record.content.lower()
                or any(query in tag for tag in record.tags)
            )
        ]
        matches.sort(key=lambda item: (item.importance, item.confidence, item.updated_at), reverse=True)
        return tuple(matches[:limit])

    def related(self, memory_id: str) -> tuple[MemoryRecord, ...]:
        record = self.get(memory_id)
        with self._lock:
            return tuple(
                self._current[related_id]
                for related_id in record.relationships
                if related_id in self._current
            )

    def stats(self) -> dict[str, int]:
        with self._lock:
            result = {domain.value: 0 for domain in MemoryDomain}
            for record in self._current.values():
                result[record.domain.value] += 1
            result["total"] = len(self._current)
            result["versions"] = sum(len(items) for items in self._history.values())
            return result

    @staticmethod
    def _normalize_set(values: Iterable[str]) -> frozenset[str]:
        return frozenset(value.strip().lower() for value in values if value.strip())

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise MemoryError(f"{field} is required")
        return cleaned

    @staticmethod
    def _score(value: float, field: str) -> float:
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise MemoryError(f"{field} must be between 0 and 1")
        return score
