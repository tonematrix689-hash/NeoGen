"""Model registry, routing policy, fallback, and quality metrics for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from threading import RLock
from time import perf_counter
from typing import Any, Callable, Iterable


class ModelRouterError(RuntimeError):
    """Base error for model routing operations."""


class ModelCapability(StrEnum):
    CHAT = "chat"
    CODING = "coding"
    REASONING = "reasoning"
    RESEARCH = "research"
    VISION = "vision"
    OCR = "ocr"
    AUDIO = "audio"
    TRANSLATION = "translation"
    EMBEDDINGS = "embeddings"
    TOOL_USE = "tool_use"
    JSON = "json"


class PrivacyLevel(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    LOCAL_ONLY = "local_only"


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    id: str
    provider: str
    name: str
    capabilities: frozenset[ModelCapability]
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    privacy_level: PrivacyLevel
    cost_score: float
    latency_score: float
    quality_score: float
    reliability_score: float
    priority: int = 0
    available: bool = True


@dataclass(frozen=True, slots=True)
class ModelRequest:
    capability: ModelCapability
    prompt: str
    context_tokens: int = 0
    require_tools: bool = False
    require_streaming: bool = False
    privacy_level: PrivacyLevel = PrivacyLevel.PUBLIC
    max_cost_score: float = 1.0
    max_latency_score: float = 1.0
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    model_id: str
    output: Any
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ModelMetrics:
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    quality_sum: float = 0.0

    @property
    def success_rate(self) -> float:
        return 0.0 if self.requests == 0 else self.successes / self.requests

    @property
    def average_latency_ms(self) -> float:
        return 0.0 if self.requests == 0 else self.total_latency_ms / self.requests

    @property
    def average_quality(self) -> float:
        return 0.0 if self.successes == 0 else self.quality_sum / self.successes


ModelHandler = Callable[[ModelRequest], Any]
QualityEvaluator = Callable[[ModelRequest, Any], float]


class ModelRouter:
    """Selects the best eligible model and fails over when providers fail."""

    def __init__(self) -> None:
        self._models: dict[str, ModelDescriptor] = {}
        self._handlers: dict[str, ModelHandler] = {}
        self._metrics: dict[str, ModelMetrics] = {}
        self._lock = RLock()

    def register(self, descriptor: ModelDescriptor, handler: ModelHandler) -> ModelDescriptor:
        self._validate_descriptor(descriptor)
        with self._lock:
            if descriptor.id in self._models:
                raise ModelRouterError(f"Model already registered: {descriptor.id}")
            self._models[descriptor.id] = descriptor
            self._handlers[descriptor.id] = handler
            self._metrics[descriptor.id] = ModelMetrics()
        return descriptor

    def set_availability(self, model_id: str, available: bool) -> ModelDescriptor:
        with self._lock:
            descriptor = self.get(model_id)
            updated = replace(descriptor, available=available)
            self._models[model_id] = updated
            return updated

    def get(self, model_id: str) -> ModelDescriptor:
        with self._lock:
            try:
                return self._models[model_id]
            except KeyError as exc:
                raise ModelRouterError(f"Unknown model: {model_id}") from exc

    def eligible(self, request: ModelRequest) -> tuple[ModelDescriptor, ...]:
        self._validate_request(request)
        with self._lock:
            candidates = [model for model in self._models.values() if self._matches(model, request)]
        candidates.sort(key=self._ranking_key, reverse=True)
        return tuple(candidates)

    def route(self, request: ModelRequest) -> ModelDescriptor:
        candidates = self.eligible(request)
        if not candidates:
            raise ModelRouterError("No eligible model satisfies the request")
        return candidates[0]

    def complete(
        self,
        request: ModelRequest,
        *,
        quality_evaluator: QualityEvaluator | None = None,
    ) -> ModelResponse:
        candidates = self.eligible(request)
        if not candidates:
            raise ModelRouterError("No eligible model satisfies the request")

        errors: list[str] = []
        for model in candidates:
            handler = self._handlers[model.id]
            started = perf_counter()
            try:
                output = handler(request)
            except Exception as exc:  # provider boundary
                latency_ms = (perf_counter() - started) * 1000
                error = f"{type(exc).__name__}: {exc}"
                errors.append(f"{model.id}: {error}")
                self._record(model.id, success=False, latency_ms=latency_ms, quality=0.0)
                continue

            latency_ms = (perf_counter() - started) * 1000
            quality = model.quality_score
            if quality_evaluator is not None:
                quality = self._score(quality_evaluator(request, output), "quality")
            self._record(model.id, success=True, latency_ms=latency_ms, quality=quality)
            return ModelResponse(model.id, output, latency_ms, True)

        raise ModelRouterError("All eligible models failed: " + "; ".join(errors))

    def metrics(self, model_id: str | None = None) -> dict[str, ModelMetrics] | ModelMetrics:
        with self._lock:
            if model_id is not None:
                self.get(model_id)
                return self._metrics[model_id]
            return dict(self._metrics)

    def leaderboard(self) -> tuple[tuple[ModelDescriptor, ModelMetrics, float], ...]:
        with self._lock:
            rows = []
            for model_id, descriptor in self._models.items():
                metrics = self._metrics[model_id]
                observed_quality = metrics.average_quality if metrics.successes else descriptor.quality_score
                score = (
                    observed_quality * 0.35
                    + metrics.success_rate * 0.25
                    + descriptor.reliability_score * 0.2
                    + (1.0 - descriptor.cost_score) * 0.1
                    + (1.0 - descriptor.latency_score) * 0.1
                )
                rows.append((descriptor, metrics, score))
        rows.sort(key=lambda row: (row[2], row[0].priority), reverse=True)
        return tuple(rows)

    def benchmark(
        self,
        requests: Iterable[ModelRequest],
        *,
        quality_evaluator: QualityEvaluator,
    ) -> tuple[ModelResponse, ...]:
        responses: list[ModelResponse] = []
        for request in requests:
            responses.append(self.complete(request, quality_evaluator=quality_evaluator))
        return tuple(responses)

    def _record(self, model_id: str, *, success: bool, latency_ms: float, quality: float) -> None:
        with self._lock:
            current = self._metrics[model_id]
            self._metrics[model_id] = ModelMetrics(
                requests=current.requests + 1,
                successes=current.successes + int(success),
                failures=current.failures + int(not success),
                total_latency_ms=current.total_latency_ms + latency_ms,
                quality_sum=current.quality_sum + (quality if success else 0.0),
            )

    def _matches(self, model: ModelDescriptor, request: ModelRequest) -> bool:
        return (
            model.available
            and request.capability in model.capabilities
            and request.context_tokens <= model.context_window
            and (not request.require_tools or model.supports_tools)
            and (not request.require_streaming or model.supports_streaming)
            and self._privacy_allows(model.privacy_level, request.privacy_level)
            and model.cost_score <= request.max_cost_score
            and model.latency_score <= request.max_latency_score
        )

    @staticmethod
    def _ranking_key(model: ModelDescriptor) -> tuple[float, int]:
        score = (
            model.quality_score * 0.4
            + model.reliability_score * 0.25
            + (1.0 - model.cost_score) * 0.15
            + (1.0 - model.latency_score) * 0.15
            + min(model.context_window / 1_000_000, 1.0) * 0.05
        )
        return score, model.priority

    @staticmethod
    def _privacy_allows(model_level: PrivacyLevel, required: PrivacyLevel) -> bool:
        order = {
            PrivacyLevel.PUBLIC: 0,
            PrivacyLevel.PRIVATE: 1,
            PrivacyLevel.LOCAL_ONLY: 2,
        }
        return order[model_level] >= order[required]

    @classmethod
    def _validate_descriptor(cls, model: ModelDescriptor) -> None:
        if not model.id.strip() or not model.provider.strip() or not model.name.strip():
            raise ModelRouterError("Model id, provider, and name are required")
        if not model.capabilities:
            raise ModelRouterError("At least one capability is required")
        if model.context_window <= 0:
            raise ModelRouterError("context_window must be positive")
        cls._score(model.cost_score, "cost_score")
        cls._score(model.latency_score, "latency_score")
        cls._score(model.quality_score, "quality_score")
        cls._score(model.reliability_score, "reliability_score")

    @classmethod
    def _validate_request(cls, request: ModelRequest) -> None:
        if not request.prompt.strip():
            raise ModelRouterError("prompt is required")
        if request.context_tokens < 0:
            raise ModelRouterError("context_tokens cannot be negative")
        cls._score(request.max_cost_score, "max_cost_score")
        cls._score(request.max_latency_score, "max_latency_score")

    @staticmethod
    def _score(value: float, field: str) -> float:
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise ModelRouterError(f"{field} must be between 0 and 1")
        return score
