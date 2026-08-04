"""Lightweight verification service for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .events import EventBus


@dataclass(frozen=True, slots=True)
class VerificationResult:
    name: str
    passed: bool
    details: dict[str, Any]


class VerificationEngine:
    """Register and run simple health and invariant checks."""

    def __init__(self, events: EventBus | None = None) -> None:
        self._events = events or EventBus()
        self._checks: dict[str, Callable[[], bool | dict[str, Any] | VerificationResult]] = {}
        self._runs = 0
        self._failures = 0

    def register(
        self,
        name: str,
        check: Callable[[], bool | dict[str, Any] | VerificationResult],
    ) -> None:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("verification check name is required")
        self._checks[cleaned] = check

    def run(self, name: str) -> VerificationResult:
        if name not in self._checks:
            raise KeyError(f"Unknown verification check: {name}")
        try:
            raw = self._checks[name]()
            if isinstance(raw, VerificationResult):
                result = raw
            elif isinstance(raw, dict):
                result = VerificationResult(name=name, passed=bool(raw.get("passed", True)), details=dict(raw))
            else:
                result = VerificationResult(name=name, passed=bool(raw), details={})
        except Exception as exc:
            result = VerificationResult(
                name=name,
                passed=False,
                details={"error": f"{type(exc).__name__}: {exc}"},
            )
        self._runs += 1
        if not result.passed:
            self._failures += 1
        self._events.publish(
            "VerificationCompleted",
            source="neogen.verification",
            payload={"name": result.name, "passed": result.passed, "details": result.details},
        )
        return result

    def run_all(self) -> tuple[VerificationResult, ...]:
        return tuple(self.run(name) for name in sorted(self._checks))

    def stats(self) -> dict[str, int]:
        return {
            "registered": len(self._checks),
            "runs": self._runs,
            "failures": self._failures,
        }
