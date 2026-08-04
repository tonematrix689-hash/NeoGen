"""SQLite-backed project memory and conversation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    project_id: str
    category: str
    content: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    id: str
    project_id: str
    conversation_id: str
    role: str
    content: str
    created_at: str


class MemoryService:
    """Durable, inspectable memory scoped by project and conversation."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    async def start(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS project_memory (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_project_memory_scope
                ON project_memory(project_id, category, created_at);
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_scope
                ON conversation_turns(project_id, conversation_id, created_at);
            """
        )
        connection.commit()
        self._connection = connection

    async def stop(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def remember(self, project_id: str, content: str, *, category: str = "general") -> MemoryRecord:
        self._validate_text("project_id", project_id)
        self._validate_text("content", content)
        self._validate_text("category", category)
        record = MemoryRecord(str(uuid4()), project_id, category, content, _now())
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                "INSERT INTO project_memory VALUES (?, ?, ?, ?, ?)",
                (record.id, record.project_id, record.category, record.content, record.created_at),
            )
            connection.commit()
        return record

    def add_turn(
        self,
        project_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> ConversationTurn:
        for name, value in (("project_id", project_id), ("conversation_id", conversation_id), ("content", content)):
            self._validate_text(name, value)
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Unsupported conversation role: {role}")
        turn = ConversationTurn(str(uuid4()), project_id, conversation_id, role, content, _now())
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                "INSERT INTO conversation_turns VALUES (?, ?, ?, ?, ?, ?)",
                (turn.id, turn.project_id, turn.conversation_id, turn.role, turn.content, turn.created_at),
            )
            connection.commit()
        return turn

    def conversation(self, project_id: str, conversation_id: str, *, limit: int = 100) -> tuple[ConversationTurn, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            rows = self._require_connection().execute(
                """SELECT * FROM conversation_turns
                   WHERE project_id = ? AND conversation_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (project_id, conversation_id, limit),
            ).fetchall()
        return tuple(self._turn(row) for row in reversed(rows))

    def search(self, project_id: str, query: str, *, limit: int = 20) -> tuple[MemoryRecord, ...]:
        self._validate_text("query", query)
        if limit < 1:
            raise ValueError("limit must be positive")
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = self._require_connection().execute(
                """SELECT * FROM project_memory
                   WHERE project_id = ? AND content LIKE ? ESCAPE '\\'
                   ORDER BY created_at DESC LIMIT ?""",
                (project_id, f"%{escaped}%", limit),
            ).fetchall()
        return tuple(self._memory(row) for row in rows)

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Memory service is not started.")
        return self._connection

    @staticmethod
    def _validate_text(name: str, value: str) -> None:
        if not value or not value.strip():
            raise ValueError(f"{name} must not be empty")

    @staticmethod
    def _memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(row["id"], row["project_id"], row["category"], row["content"], row["created_at"])

    @staticmethod
    def _turn(row: sqlite3.Row) -> ConversationTurn:
        return ConversationTurn(
            row["id"], row["project_id"], row["conversation_id"], row["role"], row["content"], row["created_at"]
        )
