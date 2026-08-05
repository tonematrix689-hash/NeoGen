"""Approval-gated command execution without a command shell."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import shlex

from genesis.app.security import PermissionEngine


@dataclass(frozen=True, slots=True)
class TerminalResult:
    exit_code: int
    stdout: str
    stderr: str


class TerminalTool:
    def __init__(self, root: Path, permissions: PermissionEngine, *, timeout_seconds: float = 30) -> None:
        self.root = root.resolve()
        self.permissions = permissions
        self.timeout_seconds = timeout_seconds

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        return None

    def request_run(self, project_id: str, arguments: tuple[str, ...]):
        self._validate(arguments)
        action = self._action(arguments)
        return self.permissions.request(project_id, "terminal.run", action, action=action)

    async def run(self, project_id: str, arguments: tuple[str, ...], approval_id: str) -> TerminalResult:
        self._validate(arguments)
        self.permissions.consume(approval_id, project_id, "terminal.run", action=self._action(arguments))
        process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=self.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"Command exceeded {self.timeout_seconds} seconds.") from None
        return TerminalResult(process.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace"))

    @staticmethod
    def _validate(arguments: tuple[str, ...]) -> None:
        if not arguments or any(not argument for argument in arguments):
            raise ValueError("Terminal arguments must be a non-empty tuple of non-empty strings.")

    @staticmethod
    def _action(arguments: tuple[str, ...]) -> str:
        return shlex.join(arguments)
