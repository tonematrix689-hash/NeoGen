"""Inspectable code changes with concurrency checks, previews, and recovery checkpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import difflib
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from genesis.app.security import ApprovalRequest, PermissionEngine


MISSING_FILE_DIGEST = "missing"
_IGNORED_PARTS = {".git", ".genesis", ".pytest_cache", "__pycache__", "node_modules", ".venv", "venv"}


@dataclass(frozen=True, slots=True)
class CodeFileSummary:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CodeFile:
    path: str
    content: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CodeChange:
    """Complete replacement content tied to the version inspected by the agent."""

    path: str
    content: str
    expected_sha256: str


@dataclass(frozen=True, slots=True)
class CodeProposal:
    approval: ApprovalRequest
    diff: str
    files: tuple[str, ...]
    total_bytes: int


class CodeWorkspaceTool:
    """Source inspection and atomic, recoverable multi-file editing."""

    def __init__(
        self,
        root: Path,
        checkpoints_root: Path,
        permissions: PermissionEngine,
        *,
        max_files_per_change: int = 32,
        max_total_bytes: int = 2_000_000,
        max_read_bytes: int = 1_000_000,
    ) -> None:
        self.root = root.resolve()
        self.checkpoints_root = checkpoints_root.resolve()
        self.permissions = permissions
        self.max_files_per_change = max_files_per_change
        self.max_total_bytes = max_total_bytes
        self.max_read_bytes = max_read_bytes

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoints_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    async def stop(self) -> None:
        return None

    def inventory(self, *, limit: int = 500) -> tuple[CodeFileSummary, ...]:
        if not 1 <= limit <= 5_000:
            raise ValueError("limit must be between 1 and 5000")
        summaries: list[CodeFileSummary] = []
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root)
            if (
                any(part in _IGNORED_PARTS for part in relative.parts)
                or path.is_symlink()
                or not path.is_file()
            ):
                continue
            size = path.stat().st_size
            if size > self.max_read_bytes:
                continue
            data = path.read_bytes()
            summaries.append(CodeFileSummary(relative.as_posix(), size, sha256(data).hexdigest()))
            if len(summaries) >= limit:
                break
        return tuple(summaries)

    def read(self, relative_path: str) -> CodeFile:
        target = self._resolve(relative_path)
        data = target.read_bytes()
        if len(data) > self.max_read_bytes:
            raise ValueError("Code file exceeds the configured read limit.")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 text source files can be edited.") from exc
        return CodeFile(self._relative(target), content, sha256(data).hexdigest())

    def missing_file(self, relative_path: str) -> CodeFile:
        target = self._resolve(relative_path)
        if target.exists():
            raise FileExistsError(self._relative(target))
        return CodeFile(self._relative(target), "", MISSING_FILE_DIGEST)

    def propose(self, project_id: str, changes: tuple[CodeChange, ...]) -> CodeProposal:
        normalized = self._validate_changes(changes)
        self._assert_versions(normalized)
        diff = self._build_diff(normalized)
        action = self._change_action(normalized)
        total_bytes = sum(len(change.content.encode("utf-8")) for change in normalized)
        approval = self.permissions.request(
            project_id,
            "code.apply",
            f"Apply {len(normalized)} source change(s), {total_bytes} bytes, with a recovery checkpoint",
            action=action,
        )
        return CodeProposal(approval, diff, tuple(change.path for change in normalized), total_bytes)

    def apply(self, project_id: str, changes: tuple[CodeChange, ...], approval_id: str) -> str:
        normalized = self._validate_changes(changes)
        self._assert_versions(normalized)
        action = self._change_action(normalized)
        self.permissions.consume(approval_id, project_id, "code.apply", action=action)
        checkpoint_id = self._create_checkpoint(project_id, normalized)
        try:
            for change in normalized:
                self._atomic_write(self._resolve(change.path), change.content)
            self._mark_checkpoint_applied(project_id, checkpoint_id)
        except Exception:
            self._restore_checkpoint_files(project_id, checkpoint_id)
            raise
        return checkpoint_id

    def request_restore(self, project_id: str, checkpoint_id: str) -> ApprovalRequest:
        manifest = self._load_manifest(project_id, checkpoint_id)
        return self.permissions.request(
            project_id,
            "code.restore",
            f"Restore {len(manifest['files'])} file(s) from checkpoint {checkpoint_id}",
            action=self._restore_action(checkpoint_id),
        )

    def restore(self, project_id: str, checkpoint_id: str, approval_id: str) -> None:
        self._load_manifest(project_id, checkpoint_id)
        self.permissions.consume(
            approval_id,
            project_id,
            "code.restore",
            action=self._restore_action(checkpoint_id),
        )
        self._restore_checkpoint_files(project_id, checkpoint_id)

    def recover_failed_change(self, project_id: str, checkpoint_id: str) -> None:
        """Immediately reverse a just-applied change after failed verification.

        The original approval explicitly includes a recovery checkpoint. This safety path is used
        only by the improvement coordinator during the same execution attempt; it cannot apply new
        content and it cannot target a different project.
        """

        manifest = self._load_manifest(project_id, checkpoint_id)
        for record in manifest["files"]:
            target = self._resolve(str(record["path"]))
            expected = record.get("applied_sha256")
            if not expected or self._current_digest(target) != expected:
                raise RuntimeError(
                    f"Automatic recovery refused because source changed during verification: "
                    f"{record['path']}"
                )
        self._restore_checkpoint_files(project_id, checkpoint_id)

    def _validate_changes(self, changes: tuple[CodeChange, ...]) -> tuple[CodeChange, ...]:
        if not changes:
            raise ValueError("At least one code change is required.")
        if len(changes) > self.max_files_per_change:
            raise ValueError("Code proposal exceeds the configured file limit.")
        normalized: list[CodeChange] = []
        seen: set[str] = set()
        total_bytes = 0
        for change in changes:
            target = self._resolve(change.path)
            path = self._relative(target)
            if target.exists() and not target.is_file():
                raise ValueError(f"Source target is not a regular file: {path}")
            if path in seen:
                raise ValueError(f"Duplicate code path: {path}")
            if change.expected_sha256 != MISSING_FILE_DIGEST and (
                len(change.expected_sha256) != 64
                or any(character not in "0123456789abcdef" for character in change.expected_sha256)
            ):
                raise ValueError(f"Invalid expected SHA-256 for {path}")
            encoded = change.content.encode("utf-8")
            total_bytes += len(encoded)
            if total_bytes > self.max_total_bytes:
                raise ValueError("Code proposal exceeds the configured byte limit.")
            seen.add(path)
            normalized.append(CodeChange(path, change.content, change.expected_sha256))
        return tuple(normalized)

    def _assert_versions(self, changes: tuple[CodeChange, ...]) -> None:
        for change in changes:
            target = self._resolve(change.path)
            actual = self._current_digest(target)
            if actual != change.expected_sha256:
                raise RuntimeError(
                    f"Source changed after inspection: {change.path} "
                    f"(expected {change.expected_sha256}, found {actual})."
                )

    def _build_diff(self, changes: tuple[CodeChange, ...]) -> str:
        parts: list[str] = []
        for change in changes:
            target = self._resolve(change.path)
            before = "" if not target.exists() else self.read(change.path).content
            parts.extend(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    change.content.splitlines(keepends=True),
                    fromfile=f"a/{change.path}",
                    tofile=f"b/{change.path}",
                )
            )
        return "".join(parts)

    def _create_checkpoint(self, project_id: str, changes: tuple[CodeChange, ...]) -> str:
        checkpoint_id = str(uuid4())
        checkpoint = self._checkpoint_path(project_id, checkpoint_id)
        originals = checkpoint / "originals"
        originals.mkdir(parents=True, exist_ok=False, mode=0o700)
        records: list[dict[str, object]] = []
        for index, change in enumerate(changes):
            target = self._resolve(change.path)
            existed = target.exists()
            backup_name = f"{index:04d}.txt" if existed else None
            if existed:
                self._atomic_write(
                    originals / backup_name,
                    target.read_text(encoding="utf-8"),
                )
            records.append(
                {
                    "path": change.path,
                    "existed": existed,
                    "backup": backup_name,
                    "sha256": self._current_digest(target),
                }
            )
        manifest = {
            "checkpoint_id": checkpoint_id,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "files": records,
        }
        self._atomic_write(checkpoint / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        return checkpoint_id

    def _mark_checkpoint_applied(self, project_id: str, checkpoint_id: str) -> None:
        manifest = self._load_manifest(project_id, checkpoint_id)
        for record in manifest["files"]:
            record["applied_sha256"] = self._current_digest(
                self._resolve(str(record["path"]))
            )
        manifest_path = self._checkpoint_path(project_id, checkpoint_id) / "manifest.json"
        self._atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True))

    def _restore_checkpoint_files(self, project_id: str, checkpoint_id: str) -> None:
        manifest = self._load_manifest(project_id, checkpoint_id)
        checkpoint = self._checkpoint_path(project_id, checkpoint_id)
        for record in manifest["files"]:
            target = self._resolve(str(record["path"]))
            if bool(record["existed"]):
                backup = checkpoint / "originals" / str(record["backup"])
                self._atomic_write(target, backup.read_text(encoding="utf-8"))
            elif target.exists():
                target.unlink()

    def _load_manifest(self, project_id: str, checkpoint_id: str) -> dict:
        if not checkpoint_id or any(character not in "0123456789abcdef-" for character in checkpoint_id):
            raise ValueError("Invalid checkpoint id.")
        manifest_path = self._checkpoint_path(project_id, checkpoint_id) / "manifest.json"
        if not manifest_path.is_file():
            raise KeyError(f"Unknown checkpoint: {checkpoint_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("project_id") != project_id or manifest.get("checkpoint_id") != checkpoint_id:
            raise PermissionError("Checkpoint does not belong to this project.")
        return manifest

    def _checkpoint_path(self, project_id: str, checkpoint_id: str) -> Path:
        scope = sha256(project_id.encode("utf-8")).hexdigest()[:24]
        return self.checkpoints_root / scope / checkpoint_id

    def _resolve(self, relative_path: str) -> Path:
        if not relative_path or not relative_path.strip():
            raise ValueError("A relative source path is required.")
        candidate = (self.root / relative_path).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise PermissionError("Source path escapes the configured workspace.")
        return candidate

    def _relative(self, target: Path) -> str:
        return target.relative_to(self.root).as_posix()

    @staticmethod
    def _current_digest(target: Path) -> str:
        return sha256(target.read_bytes()).hexdigest() if target.is_file() else MISSING_FILE_DIGEST

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _change_action(changes: tuple[CodeChange, ...]) -> str:
        return json.dumps([asdict(change) for change in changes], sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _restore_action(checkpoint_id: str) -> str:
        return json.dumps({"checkpoint_id": checkpoint_id}, sort_keys=True)
