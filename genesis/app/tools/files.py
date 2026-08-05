"""File operations restricted to an explicit workspace root."""

from __future__ import annotations

from pathlib import Path

from genesis.app.security import PermissionEngine


class WorkspaceFileTool:
    def __init__(self, root: Path, permissions: PermissionEngine) -> None:
        self.root = root.resolve()
        self.permissions = permissions

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        return None

    def read_text(self, relative_path: str) -> str:
        return self._resolve(relative_path).read_text(encoding="utf-8")

    def request_write(self, project_id: str, relative_path: str, content: str):
        target = self._resolve(relative_path)
        action = self._write_action(target, content)
        return self.permissions.request(
            project_id,
            "files.write",
            f"Write {len(content.encode('utf-8'))} bytes to {target.relative_to(self.root)}",
            action=action,
        )

    def write_text(self, project_id: str, relative_path: str, content: str, approval_id: str) -> Path:
        target = self._resolve(relative_path)
        self.permissions.consume(
            approval_id, project_id, "files.write", action=self._write_action(target, content)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def _resolve(self, relative_path: str) -> Path:
        if not relative_path or not relative_path.strip():
            raise ValueError("relative_path must not be empty")
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError("Path escapes the configured workspace.")
        if candidate == self.root:
            raise PermissionError("A file path is required.")
        return candidate

    def _write_action(self, target: Path, content: str) -> str:
        return f"{target.relative_to(self.root)}\0{content}"
