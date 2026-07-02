"""Runtime settings for the Genesis kernel.

The settings module is intentionally small and standard-library-only. It must be available before
database, authentication, AI, desktop UI, or capability systems are registered.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _read_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class GenesisSettings:
    """Immutable boot settings used by the kernel."""

    environment: str = "development"
    app_name: str = "Genesis"
    log_level: str = "INFO"
    data_dir: Path = Path(".genesis")
    event_history_limit: int = 500
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 30.0
    debug: bool = False

    @classmethod
    def from_env(cls, prefix: str = "GENESIS_") -> "GenesisSettings":
        """Build settings from process environment variables."""

        data_dir = Path(os.getenv(f"{prefix}DATA_DIR", ".genesis")).expanduser()
        return cls(
            environment=os.getenv(f"{prefix}ENVIRONMENT", "development"),
            app_name=os.getenv(f"{prefix}APP_NAME", "Genesis"),
            log_level=os.getenv(f"{prefix}LOG_LEVEL", "INFO"),
            data_dir=data_dir,
            event_history_limit=int(os.getenv(f"{prefix}EVENT_HISTORY_LIMIT", "500")),
            startup_timeout_seconds=float(os.getenv(f"{prefix}STARTUP_TIMEOUT_SECONDS", "30")),
            shutdown_timeout_seconds=float(os.getenv(f"{prefix}SHUTDOWN_TIMEOUT_SECONDS", "30")),
            debug=_read_bool(os.getenv(f"{prefix}DEBUG"), False),
        )

    def ensure_directories(self) -> None:
        """Create directories required for kernel-local runtime state."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
