"""Weighted verification checks and confidence reports for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any, Callable
from uuid import uuid4

from .events import EventBus


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


VerificationHandler = Callable[..., object]


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    id: str
    name: str
    description: str
    handler: VerificationHandler
    required: bool
    weight: float


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """One normalized check result.

    The first three fields retain compatibility with the original lightweight service.
    """

    name: str
    passed: bool
    details: dict[str, Any]
    status: VerificationStatus | None = None
    message: str = ""
    confidence: float = 0.0
    check_id: str = ""
    required: bool = True
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.status is None:
            object.__setattr__(
                self,
                "status",
                VerificationStatus.PASSED if self.passed else VerificationStatus.FAILED,
            )
        if self.confidence == 0.0 and self.passed:
            object.__setattr__(self, "confidence", 1.0)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    subject: str
    passed: bool
    confidence: float
    results: tuple[VerificationResult, ...]


class VerificationEngine:
    """Register checks, normalize their evidence, and report weighted confidence."""

    def __init__(self, events: EventBus | None = None) -> None:
        self._events = events or EventBus()
        self._checks: dict[str, VerificationCheck] = {}
        self._names: dict[str, str] = {}
        self._runs = 0
        self._failures = 0

    def register(
        self,
        name: str,
        check: VerificationHandler | str | None = None,
        handler: VerificationHandler | None = None,
        *,
        description: str = "",
        required: bool = True,
        weight: float = 1.0,
    ) -> VerificationCheck:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("verification check name is required")
        if isinstance(check, str):
            if description:
                raise ValueError("description was provided twice")
            description = check
        elif callable(check):
            if handler is not None:
                raise ValueError("verification handler was provided twice")
            handler = check
        elif check is not None:
            raise TypeError("check must be a description, callable, or None")
        if handler is None or not callable(handler):
            raise ValueError("verification handler is required")
        if cleaned in self._names:
            raise ValueError(f"verification check is already registered: {cleaned}")
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("verification weight must be a positive finite number")
        registered = VerificationCheck(
            id=f"verification:{uuid4()}",
            name=cleaned,
            description=description.strip(),
            handler=handler,
            required=bool(required),
            weight=float(weight),
        )
        self._checks[registered.id] = registered
        self._names[registered.name] = registered.id
        return registered

    def run(self, name: str) -> VerificationResult:
        """Run one legacy no-argument check by name or identifier."""

        registered = self._require(name)
        result = self._execute(registered, None, pass_value=False)
        self._publish_result(result)
        return result

    def run_all(self) -> tuple[VerificationResult, ...]:
        return tuple(self.run(name) for name in sorted(self._names))

    def verify(
        self,
        *,
        subject: str,
        value: object,
        check_ids: list[str] | tuple[str, ...],
    ) -> VerificationReport:
        cleaned_subject = subject.strip()
        if not cleaned_subject:
            raise ValueError("verification subject is required")
        if not check_ids:
            raise ValueError("at least one verification check is required")
        registered = tuple(self._require(identifier) for identifier in check_ids)
        results = tuple(self._execute(check, value, pass_value=True) for check in registered)
        required_passed = all(result.passed for result in results if result.required)
        total_weight = sum(result.weight for result in results)
        confidence = sum(result.confidence * result.weight for result in results) / total_weight
        report = VerificationReport(cleaned_subject, required_passed, confidence, results)
        self._events.publish(
            "VerificationReportCompleted",
            source="neogen.verification",
            payload={
                "subject": report.subject,
                "passed": report.passed,
                "confidence": report.confidence,
                "checks": len(report.results),
            },
        )
        return report

    def stats(self) -> dict[str, int]:
        return {
            "registered": len(self._checks),
            "runs": self._runs,
            "failures": self._failures,
        }

    def _require(self, name_or_id: str) -> VerificationCheck:
        identifier = self._names.get(name_or_id, name_or_id)
        try:
            return self._checks[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown verification check: {name_or_id}") from exc

    def _execute(
        self,
        check: VerificationCheck,
        value: object,
        *,
        pass_value: bool,
    ) -> VerificationResult:
        try:
            raw = check.handler(value) if pass_value else check.handler()
            result = self._normalize(check, raw)
        except Exception as exc:
            result = VerificationResult(
                name=check.name,
                passed=False,
                details={"error_type": type(exc).__name__},
                status=VerificationStatus.ERROR,
                message=str(exc),
                confidence=0.0,
                check_id=check.id,
                required=check.required,
                weight=check.weight,
            )
        self._runs += 1
        if not result.passed:
            self._failures += 1
        return result

    @staticmethod
    def _normalize(check: VerificationCheck, raw: object) -> VerificationResult:
        if isinstance(raw, VerificationResult):
            return VerificationResult(
                name=raw.name or check.name,
                passed=raw.passed,
                details=dict(raw.details),
                status=raw.status,
                message=raw.message,
                confidence=raw.confidence,
                check_id=raw.check_id or check.id,
                required=check.required,
                weight=check.weight,
            )
        if isinstance(raw, tuple) and len(raw) == 4:
            passed, message, details, confidence = raw
        elif isinstance(raw, dict):
            passed = bool(raw.get("passed", True))
            message = str(raw.get("message", ""))
            details = dict(raw)
            confidence = raw.get("confidence", 1.0 if passed else 0.0)
        else:
            passed = bool(raw)
            message = ""
            details = {}
            confidence = 1.0 if passed else 0.0
        numeric_confidence = float(confidence)
        if not math.isfinite(numeric_confidence) or not 0.0 <= numeric_confidence <= 1.0:
            raise ValueError("verification confidence must be between 0 and 1")
        normalized_details = dict(details)
        return VerificationResult(
            name=check.name,
            passed=bool(passed),
            details=normalized_details,
            status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
            message=str(message),
            confidence=numeric_confidence,
            check_id=check.id,
            required=check.required,
            weight=check.weight,
        )

    def _publish_result(self, result: VerificationResult) -> None:
        self._events.publish(
            "VerificationCompleted",
            source="neogen.verification",
            payload={
                "name": result.name,
                "passed": result.passed,
                "status": result.status,
                "confidence": result.confidence,
                "details": result.details,
            },
        )
