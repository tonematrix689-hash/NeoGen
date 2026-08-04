"""Governed terminal execution confined to the NeoGen workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .events import EventBus, EventSeverity


class TerminalError(RuntimeError):
    """Raised when a terminal request is invalid, denied, or fails."""


@dataclass(frozen=True, slots=True)
class TerminalResult:
    command: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    truncated: bool


class TerminalService:
    """Run approved commands without a shell inside a sandboxed workspace root."""

    DEFAULT_ALLOWED = frozenset(
        {
            "python",
            "python3",
            "py",
            "git",
            "node",
            "npm",
            "npx",
            "pytest",
            "ruff",
            "mypy",
            "pip",
            "pip3",
        }
    )

    SAFE_ENV_KEYS = frozenset(
        {
            "PATH",
            "HOME",
            "USERPROFILE",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "NODE_PATH",
        }
    )

    def __init__(
        self,
        workspace_root: str | Path,
        events: EventBus | None = None,
        *,
        allowed_commands: Iterable[str] | None = None,
        default_timeout_seconds: int = 30,
        max_timeout_seconds: int = 120,
        max_output_bytes: int = 200_000,
    ) -> None:
        self._root = Path(workspace_root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._events = events or EventBus()
        self._allowed = frozenset(allowed_commands or self.DEFAULT_ALLOWED)
        self._default_timeout = default_timeout_seconds
        self._max_timeout = max_timeout_seconds
        self._max_output = max_output_bytes
        self._executions = 0
        self._failures = 0
        self._timeouts = 0

    def execute(
        self,
        command: list[str] | tuple[str, ...],
        *,
        cwd: str = "",
        timeout_seconds: int | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> TerminalResult:
        argv = self._validate_command(command)
        workdir = self._resolve_cwd(cwd)
        timeout = self._validate_timeout(timeout_seconds)
        process_env = self._safe_environment(env)
        started = time.monotonic()
        self._events.publish(
            "TerminalCommandStarted",
            source="neogen.terminal",
            payload={"command": list(argv), "cwd": str(workdir), "timeout_seconds": timeout},
        )

        try:
            completed = subprocess.run(
                list(argv),
                cwd=workdir,
                env=process_env,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
            timed_out = False
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            self._timeouts += 1
            stdout = self._decode_timeout_output(exc.stdout)
            stderr = self._decode_timeout_output(exc.stderr)
            exit_code = 124
        except OSError as exc:
            self._failures += 1
            self._events.publish(
                "TerminalCommandFailed",
                source="neogen.terminal",
                severity=EventSeverity.ERROR,
                payload={"command": list(argv), "cwd": str(workdir), "error": str(exc)},
            )
            raise TerminalError(f"Unable to execute command: {exc}") from exc

        stdout, stdout_truncated = self._truncate(stdout)
        stderr, stderr_truncated = self._truncate(stderr)
        duration_ms = int((time.monotonic() - started) * 1000)
        result = TerminalResult(
            command=argv,
            cwd=workdir.relative_to(self._root).as_posix() or ".",
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            truncated=stdout_truncated or stderr_truncated,
        )
        self._executions += 1
        if exit_code != 0:
            self._failures += 1
        self._events.publish(
            "TerminalCommandCompleted",
            source="neogen.terminal",
            severity=EventSeverity.WARNING if exit_code != 0 else EventSeverity.INFO,
            payload={
                "command": list(argv),
                "cwd": result.cwd,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "timed_out": timed_out,
                "truncated": result.truncated,
            },
        )
        return result

    def available_commands(self) -> tuple[str, ...]:
        return tuple(sorted(command for command in self._allowed if shutil.which(command)))

    def stats(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self._root),
            "allowed_commands": len(self._allowed),
            "available_commands": len(self.available_commands()),
            "executions": self._executions,
            "failures": self._failures,
            "timeouts": self._timeouts,
        }

    def _validate_command(self, command: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(command, (list, tuple)) or not command:
            raise TerminalError("command must be a non-empty argument list")
        argv = tuple(str(value) for value in command)
        executable = Path(argv[0]).name.lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable not in self._allowed:
            raise TerminalError(f"Command is not allowed: {argv[0]}")
        if shutil.which(argv[0]) is None:
            raise TerminalError(f"Command is not installed: {argv[0]}")
        if any("\x00" in value for value in argv):
            raise TerminalError("Command contains a null byte")
        if sum(len(value) for value in argv) > 32_000:
            raise TerminalError("Command is too long")
        return argv

    def _resolve_cwd(self, cwd: str) -> Path:
        candidate = (self._root / cwd.strip()).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise TerminalError("Working directory escapes workspace root") from exc
        if not candidate.exists() or not candidate.is_dir():
            raise TerminalError(f"Working directory does not exist: {cwd}")
        if candidate.is_symlink():
            raise TerminalError("Symbolic-link working directories are not supported")
        return candidate

    def _validate_timeout(self, timeout_seconds: int | None) -> int:
        timeout = self._default_timeout if timeout_seconds is None else int(timeout_seconds)
        if timeout < 1 or timeout > self._max_timeout:
            raise TerminalError(f"timeout_seconds must be between 1 and {self._max_timeout}")
        return timeout

    def _safe_environment(self, supplied: dict[str, str] | None) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in self.SAFE_ENV_KEYS
        }
        for key, value in (supplied or {}).items():
            normalized = str(key).upper()
            if normalized not in self.SAFE_ENV_KEYS:
                raise TerminalError(f"Environment variable is not allowed: {key}")
            if "\x00" in str(value):
                raise TerminalError("Environment value contains a null byte")
            environment[str(key)] = str(value)
        return environment

    def _truncate(self, value: str) -> tuple[str, bool]:
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) <= self._max_output:
            return value, False
        clipped = encoded[: self._max_output].decode("utf-8", errors="replace")
        return clipped + "\n[output truncated]", True

    @staticmethod
    def _decode_timeout_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value
