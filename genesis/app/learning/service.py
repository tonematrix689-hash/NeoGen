"""Small, inspectable online learning for strategy selection.

The service stores outcome labels rather than prompts, source code, or model inputs. It uses a
deterministic upper-confidence-bound score to balance strategies that have worked with strategies
that need more evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    id: str
    project_id: str
    task_kind: str
    strategy: str
    reward: float
    source: str
    created_at: str


@dataclass(frozen=True, slots=True)
class StrategyScore:
    strategy: str
    observations: int
    mean_reward: float
    exploration_bonus: float
    score: float


class LearningService:
    """Persistent, project-isolated outcome learning with deterministic ranking."""

    def __init__(self, database_path: Path, *, exploration: float = 1.0) -> None:
        if exploration < 0:
            raise ValueError("exploration must not be negative")
        self.database_path = database_path
        self.exploration = exploration
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    async def start(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_outcomes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                task_kind TEXT NOT NULL,
                strategy TEXT NOT NULL,
                reward REAL NOT NULL CHECK(reward >= 0.0 AND reward <= 1.0),
                source TEXT NOT NULL CHECK(source IN ('user', 'verification', 'system')),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_learning_scope
                ON learning_outcomes(project_id, task_kind, strategy, created_at);
            """
        )
        connection.commit()
        self._connection = connection

    async def stop(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def record_outcome(
        self,
        project_id: str,
        task_kind: str,
        strategy: str,
        reward: float,
        *,
        source: str = "verification",
    ) -> OutcomeRecord:
        for name, value in (
            ("project_id", project_id),
            ("task_kind", task_kind),
            ("strategy", strategy),
        ):
            self._validate_label(name, value)
        if not 0.0 <= reward <= 1.0 or not math.isfinite(reward):
            raise ValueError("reward must be a finite value between 0 and 1")
        if source not in {"user", "verification", "system"}:
            raise ValueError(f"Unsupported outcome source: {source}")
        record = OutcomeRecord(
            str(uuid4()),
            project_id,
            task_kind,
            strategy,
            float(reward),
            source,
            datetime.now(UTC).isoformat(),
        )
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                "INSERT INTO learning_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.project_id,
                    record.task_kind,
                    record.strategy,
                    record.reward,
                    record.source,
                    record.created_at,
                ),
            )
            connection.commit()
        return record

    def rank_strategies(
        self,
        project_id: str,
        task_kind: str,
        candidates: tuple[str, ...],
    ) -> tuple[StrategyScore, ...]:
        self._validate_label("project_id", project_id)
        self._validate_label("task_kind", task_kind)
        if not candidates:
            raise ValueError("At least one strategy candidate is required.")
        if len(candidates) != len(set(candidates)):
            raise ValueError("Strategy candidates must be unique.")
        for candidate in candidates:
            self._validate_label("strategy", candidate)
        placeholders = ",".join("?" for _ in candidates)
        with self._lock:
            rows = self._require_connection().execute(
                f"""SELECT strategy, COUNT(*) AS observations, AVG(reward) AS mean_reward
                    FROM learning_outcomes
                    WHERE project_id = ? AND task_kind = ? AND strategy IN ({placeholders})
                    GROUP BY strategy""",
                (project_id, task_kind, *candidates),
            ).fetchall()
        aggregates = {
            row["strategy"]: (int(row["observations"]), float(row["mean_reward"]))
            for row in rows
        }
        total = sum(observations for observations, _ in aggregates.values())
        scores: list[StrategyScore] = []
        for strategy in candidates:
            observations, mean_reward = aggregates.get(strategy, (0, 0.0))
            if observations == 0:
                bonus = self.exploration * math.sqrt(2.0 * math.log(max(total, 1) + 1))
                score = bonus
            else:
                bonus = self.exploration * math.sqrt(
                    2.0 * math.log(max(total, 1) + 1) / observations
                )
                score = mean_reward + bonus
            scores.append(StrategyScore(strategy, observations, mean_reward, bonus, score))
        return tuple(
            sorted(
                scores,
                key=lambda result: (
                    result.observations != 0,
                    -result.score,
                    result.strategy,
                ),
            )
        )

    def outcomes(
        self, project_id: str, task_kind: str, *, limit: int = 100
    ) -> tuple[OutcomeRecord, ...]:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        with self._lock:
            rows = self._require_connection().execute(
                """SELECT * FROM learning_outcomes
                   WHERE project_id = ? AND task_kind = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (project_id, task_kind, limit),
            ).fetchall()
        return tuple(
            OutcomeRecord(
                row["id"],
                row["project_id"],
                row["task_kind"],
                row["strategy"],
                float(row["reward"]),
                row["source"],
                row["created_at"],
            )
            for row in rows
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Learning service is not started.")
        return self._connection

    @staticmethod
    def _validate_label(name: str, value: str) -> None:
        if not value or not value.strip():
            raise ValueError(f"{name} must not be empty")
        if len(value) > 200:
            raise ValueError(f"{name} exceeds 200 characters")
