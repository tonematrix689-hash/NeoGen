"""Inspect and mutate an authorized Git checkout with exact approvals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess

from genesis.app.security import PermissionEngine


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    root: str
    available: bool
    branch: str | None
    commit: str | None
    dirty: bool
    remotes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepositoryResult:
    arguments: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str


class RepositoryService:
    """Git access scoped to one configured workspace root.

    Commands are passed directly to ``git``; no command shell is involved.
    Every mutation is approved against its exact argument vector and can run
    only once.
    """

    def __init__(
        self,
        root: Path,
        permissions: PermissionEngine,
        *,
        timeout_seconds: float = 120,
    ) -> None:
        self.root = root.resolve()
        self.permissions = permissions
        self.timeout_seconds = timeout_seconds

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        return None

    def snapshot(self) -> RepositorySnapshot:
        if not (self.root / ".git").exists():
            return RepositorySnapshot(str(self.root), False, None, None, False, ())
        branch = self._read("branch", "--show-current").strip() or None
        commit = self._read("rev-parse", "HEAD").strip() or None
        dirty = bool(self._read("status", "--porcelain").strip())
        remotes = tuple(line.strip() for line in self._read("remote").splitlines() if line.strip())
        return RepositorySnapshot(str(self.root), True, branch, commit, dirty, remotes)

    def status(self) -> str:
        self._require_repository()
        return self._read("status", "--short", "--branch")

    def diff(self, *paths: str) -> str:
        self._require_repository()
        arguments = ["diff", "--"]
        arguments.extend(paths)
        return self._read(*arguments)

    def log(self, *, limit: int = 25) -> str:
        self._require_repository()
        bounded = max(1, min(int(limit), 200))
        return self._read("log", f"-{bounded}", "--oneline", "--decorate")

    def request(self, project_id: str, arguments: tuple[str, ...]):
        self._validate(arguments)
        self._require_repository()
        action = self._action(arguments)
        return self.permissions.request(
            project_id,
            "repository.git",
            f"Run {action} in {self.root.name}",
            action=action,
        )

    async def run(
        self,
        project_id: str,
        arguments: tuple[str, ...],
        approval_id: str,
    ) -> RepositoryResult:
        self._validate(arguments)
        self._require_repository()
        self.permissions.consume(
            approval_id,
            project_id,
            "repository.git",
            action=self._action(arguments),
        )
        process = await asyncio.create_subprocess_exec(
            "git",
            *arguments,
            cwd=self.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(
                f"Git operation exceeded {self.timeout_seconds} seconds."
            ) from None
        return RepositoryResult(
            arguments,
            process.returncode,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )

    def _read(self, *arguments: str) -> str:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=min(self.timeout_seconds, 30),
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "Git inspection failed")
        return completed.stdout

    def _require_repository(self) -> None:
        if not (self.root / ".git").exists():
            raise ValueError(f"Configured workspace is not a Git checkout: {self.root}")

    @staticmethod
    def _validate(arguments: tuple[str, ...]) -> None:
        if not arguments or any(not isinstance(item, str) or not item for item in arguments):
            raise ValueError("Git arguments must be non-empty strings.")

    @staticmethod
    def _action(arguments: tuple[str, ...]) -> str:
        return shlex.join(("git", *arguments))
