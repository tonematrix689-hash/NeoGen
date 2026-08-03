"""Dependency-free durable storage primitives for NeoGen."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator


class StorageError(RuntimeError):
    """Base error for persistence operations."""


@dataclass(frozen=True, slots=True)
class StoredRecord:
    namespace: str
    key: str
    value: Any
    version: int
    created_at: datetime
    updated_at: datetime


class SQLiteStore:
    """Thread-safe namespaced JSON document store backed by SQLite."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS neogen_records (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, key)
                );
                CREATE INDEX IF NOT EXISTS idx_neogen_records_namespace
                ON neogen_records(namespace);
                CREATE TABLE IF NOT EXISTS neogen_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO neogen_metadata(key, value)
                VALUES ('schema_version', '1');
                """
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def put(self, namespace: str, key: str, value: Any, *, expected_version: int | None = None) -> StoredRecord:
        ns = self._required(namespace, "namespace")
        normalized_key = self._required(key, "key")
        payload = self._encode(value)
        now = datetime.now(timezone.utc)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT version, created_at FROM neogen_records WHERE namespace = ? AND key = ?",
                (ns, normalized_key),
            ).fetchone()
            if row is None:
                if expected_version not in {None, 0}:
                    raise StorageError("Version conflict: record does not exist")
                version = 1
                created_at = now
                connection.execute(
                    "INSERT INTO neogen_records(namespace,key,value_json,version,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (ns, normalized_key, payload, version, created_at.isoformat(), now.isoformat()),
                )
            else:
                current_version = int(row["version"])
                if expected_version is not None and expected_version != current_version:
                    raise StorageError(f"Version conflict: expected {expected_version}, found {current_version}")
                version = current_version + 1
                created_at = datetime.fromisoformat(row["created_at"])
                connection.execute(
                    "UPDATE neogen_records SET value_json = ?, version = ?, updated_at = ? WHERE namespace = ? AND key = ?",
                    (payload, version, now.isoformat(), ns, normalized_key),
                )
        return StoredRecord(ns, normalized_key, value, version, created_at, now)

    def get(self, namespace: str, key: str) -> StoredRecord:
        ns = self._required(namespace, "namespace")
        normalized_key = self._required(key, "key")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM neogen_records WHERE namespace = ? AND key = ?",
                (ns, normalized_key),
            ).fetchone()
        if row is None:
            raise StorageError(f"Unknown record: {ns}/{normalized_key}")
        return self._row_to_record(row)

    def delete(self, namespace: str, key: str, *, expected_version: int | None = None) -> StoredRecord:
        record = self.get(namespace, key)
        if expected_version is not None and expected_version != record.version:
            raise StorageError(f"Version conflict: expected {expected_version}, found {record.version}")
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM neogen_records WHERE namespace = ? AND key = ?",
                (record.namespace, record.key),
            )
        return record

    def list(self, namespace: str, *, prefix: str = "", limit: int = 1000) -> tuple[StoredRecord, ...]:
        ns = self._required(namespace, "namespace")
        if limit <= 0:
            raise StorageError("limit must be positive")
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM neogen_records WHERE namespace = ? AND key LIKE ? ORDER BY key LIMIT ?",
                (ns, f"{prefix}%", limit),
            ).fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    def namespaces(self) -> tuple[str, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT DISTINCT namespace FROM neogen_records ORDER BY namespace"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM neogen_records ORDER BY namespace, key"
            ).fetchall()
        return {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "records": [
                {
                    "namespace": row["namespace"],
                    "key": row["key"],
                    "value": json.loads(row["value_json"]),
                    "version": row["version"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ],
        }

    def restore(self, snapshot: dict[str, Any], *, replace: bool = False) -> int:
        if int(snapshot.get("schema_version", 0)) != 1:
            raise StorageError("Unsupported snapshot schema version")
        records = snapshot.get("records")
        if not isinstance(records, list):
            raise StorageError("Snapshot records must be a list")
        with self.transaction() as connection:
            if replace:
                connection.execute("DELETE FROM neogen_records")
            count = 0
            for item in records:
                connection.execute(
                    """
                    INSERT INTO neogen_records(namespace,key,value_json,version,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(namespace,key) DO UPDATE SET
                      value_json=excluded.value_json,
                      version=excluded.version,
                      created_at=excluded.created_at,
                      updated_at=excluded.updated_at
                    """,
                    (
                        self._required(str(item["namespace"]), "namespace"),
                        self._required(str(item["key"]), "key"),
                        self._encode(item["value"]),
                        int(item["version"]),
                        str(item["created_at"]),
                        str(item["updated_at"]),
                    ),
                )
                count += 1
        return count

    def backup_to(self, destination: str | Path) -> Path:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination_path))
            try:
                self._connection.backup(target)
            finally:
                target.close()
        return destination_path

    def stats(self) -> dict[str, int | str]:
        with self._lock:
            record_count = int(self._connection.execute("SELECT COUNT(*) FROM neogen_records").fetchone()[0])
            namespace_count = int(self._connection.execute("SELECT COUNT(DISTINCT namespace) FROM neogen_records").fetchone()[0])
        return {
            "backend": "sqlite",
            "records": record_count,
            "namespaces": namespace_count,
            "schema_version": 1,
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _row_to_record(self, row: sqlite3.Row) -> StoredRecord:
        return StoredRecord(
            namespace=str(row["namespace"]),
            key=str(row["key"]),
            value=json.loads(row["value_json"]),
            version=int(row["version"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _encode(value: Any) -> str:
        try:
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise StorageError("value must be JSON serializable") from exc

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise StorageError(f"{field} is required")
        return cleaned
