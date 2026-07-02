"""Configuration access for Genesis services and capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from genesis.app.kernel.settings import GenesisSettings


class ConfigurationError(RuntimeError):
    """Raised when a required configuration value is missing or invalid."""


class ConfigProvider:
    """Read-only typed access to kernel configuration values."""

    def __init__(self, settings: GenesisSettings, overrides: Mapping[str, Any] | None = None) -> None:
        self._settings = settings
        self._values: dict[str, Any] = asdict(settings)
        if overrides:
            self._values.update(dict(overrides))

    @property
    def settings(self) -> GenesisSettings:
        """Return the immutable kernel settings object."""

        return self._settings

    def get(self, key: str, default: Any = None) -> Any:
        """Return a configuration value or a default."""

        return self._values.get(key, default)

    def require(self, key: str) -> Any:
        """Return a configuration value, raising if it is absent."""

        if key not in self._values or self._values[key] is None:
            raise ConfigurationError(f"Required configuration value is missing: {key}")
        return self._values[key]

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy suitable for diagnostics."""

        return dict(self._values)
