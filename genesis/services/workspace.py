"""Sandboxed project workspace file operations for NeoGen."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import EventBus


class WorkspaceError(RuntimeError):
    """Raised when a workspace operation is invalid or denied."""


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    path: str
    name: str
    kind: str
    size: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class FileDocument:
    path: str
    content: str
    size: int
    sha256: str
    modified_at: datetime


class WorkspaceService:
    """Provide path-safe file operations inside a single configured root."""

    def __init__(
        self,
        root: str | Path,
        events: EventBus | None = None,
        *,
        max_file_bytes: int = 2_000_000,
    ) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._events = events or EventBus()
        self._max_file_bytes = max_file_bytes

    @property
    def root(self) -> Path:
        return self._root

    def list(self, path: str = "", *, recursive: bool = False) -> tuple[WorkspaceEntry, ...]:
        target = self._resolve(path)
        if not target.exists():
            raise WorkspaceError(f"Path does not exist: {path}")
        if not target.is_dir():
            raise WorkspaceError(f"Path is not a directory: {path}")
        iterator = target.rglob("*") if recursive else target.iterdir()
        entries = []
        for item in iterator:
            if item.is_symlink():
                continue
            stat = item.stat()
            entries.append(
                WorkspaceEntry(
                    path=item.relative_to(self._root).as_posix(),
                    name=item.name,
                    kind="directory" if item.is_dir() else "file",
                    size=0 if item.is_dir() else stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                )
            )
        return tuple(sorted(entries, key=lambda value: (value.kind != "directory", value.path.lower())))

    def read(self, path: str) -> FileDocument:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceError(f"File does not exist: {path}")
        size = target.stat().st_size
        if size > self._max_file_bytes:
            raise WorkspaceError(f"File exceeds {self._max_file_bytes} byte limit")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Only UTF-8 text files are supported") from exc
        document = self._document(target, content)
        self._publish("WorkspaceFileRead", path=document.path, size=document.size)
        return document

    def write(
        self,
        path: str,
        content: str,
        *,
        create_parents: bool = True,
        expected_sha256: str | None = None,
    ) -> FileDocument:
        encoded = content.encode("utf-8")
        if len(encoded) > self._max_file_bytes:
            raise WorkspaceError(f"File exceeds {self._max_file_bytes} byte limit")
        target = self._resolve(path)
        if target.exists() and target.is_dir():
            raise WorkspaceError("Cannot overwrite a directory")
        if expected_sha256 is not None:
            if not target.exists():
                raise WorkspaceError("Expected checksum supplied for a missing file")
            current = hashlib.sha256(target.read_bytes()).hexdigest()
            if current != expected_sha256:
                raise WorkspaceError("File changed since it was read")
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise WorkspaceError("Parent directory does not exist")
        temporary = target.with_name(f".{target.name}.neogen.tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, target)
        document = self._document(target, content)
        self._publish("WorkspaceFileWritten", path=document.path, size=document.size)
        return document

    def create_directory(self, path: str) -> WorkspaceEntry:
        target = self._resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        stat = target.stat()
        entry = WorkspaceEntry(
            path=target.relative_to(self._root).as_posix(),
            name=target.name,
            kind="directory",
            size=0,
            modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
        )
        self._publish("WorkspaceDirectoryCreated", path=entry.path)
        return entry

    def delete(self, path: str, *, recursive: bool = False) -> dict[str, Any]:
        target = self._resolve(path)
        if target == self._root:
            raise WorkspaceError("Workspace root cannot be deleted")
        if not target.exists():
            raise WorkspaceError(f"Path does not exist: {path}")
        relative = target.relative_to(self._root).as_posix()
        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
            kind = "directory"
        else:
            target.unlink()
            kind = "file"
        self._publish("WorkspacePathDeleted", path=relative, kind=kind)
        return {"deleted": True, "path": relative, "kind": kind}

    def stats(self) -> dict[str, int | str]:
        files = 0
        directories = 0
        total_bytes = 0
        for item in self._root.rglob("*"):
            if item.is_symlink():
                continue
            if item.is_dir():
                directories += 1
            elif item.is_file():
                files += 1
                total_bytes += item.stat().st_size
        return {
            "root": str(self._root),
            "files": files,
            "directories": directories,
            "bytes": total_bytes,
        }

    def _resolve(self, path: str) -> Path:
        cleaned = path.strip().replace("\\", "/")
        candidate = (self._root / cleaned).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise WorkspaceError("Path escapes workspace root") from exc
        if candidate.is_symlink():
            raise WorkspaceError("Symbolic links are not supported")
        return candidate

    def _document(self, target: Path, content: str) -> FileDocument:
        stat = target.stat()
        return FileDocument(
            path=target.relative_to(self._root).as_posix(),
            content=content,
            size=stat.st_size,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
        )

    def _publish(self, event_type: str, **payload: Any) -> None:
        self._events.publish(event_type, source="neogen.workspace", payload=payload)
