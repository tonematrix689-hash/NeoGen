"""Governed media mission contracts for Afterlife Neogenesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
from typing import Any
from uuid import uuid4


class MediaMissionError(RuntimeError):
    """Raised when a media mission transition is invalid."""


class MissionState(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    PREVIEW_READY = "preview_ready"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssetKind(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    LYRICS = "lyrics"
    CAPTIONS = "captions"
    THUMBNAIL = "thumbnail"
    METADATA = "metadata"


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    provider: str
    model: str
    prompt: str
    created_at: datetime
    source_uris: tuple[str, ...] = ()
    licence: str = "unspecified"
    user_supplied: bool = False

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt,
            "created_at": self.created_at.astimezone(UTC).isoformat(),
            "source_uris": list(self.source_uris),
            "licence": self.licence,
            "user_supplied": self.user_supplied,
        }


@dataclass(frozen=True, slots=True)
class MediaAsset:
    asset_id: str
    kind: AssetKind
    uri: str
    sha256: str
    bytes_size: int
    provenance: ProvenanceRecord

    @classmethod
    def from_bytes(cls, *, kind: AssetKind, uri: str, content: bytes, provenance: ProvenanceRecord) -> "MediaAsset":
        if not uri.strip():
            raise ValueError("Asset URI is required.")
        return cls(str(uuid4()), kind, uri, hashlib.sha256(content).hexdigest(), len(content), provenance)


@dataclass(frozen=True, slots=True)
class PublishApproval:
    approved_by: str
    approved_at: datetime
    preview_digest: str
    confirmation: str


@dataclass(slots=True)
class MediaMission:
    title: str
    brief: str
    destination: str = "youtube"
    mission_id: str = field(default_factory=lambda: str(uuid4()))
    state: MissionState = MissionState.DRAFT
    assets: list[MediaAsset] = field(default_factory=list)
    approval: PublishApproval | None = None
    published_url: str | None = None
    failure_reason: str | None = None

    def begin_generation(self) -> None:
        self._require_state(MissionState.DRAFT)
        self.state = MissionState.GENERATING

    def add_asset(self, asset: MediaAsset) -> None:
        if self.state not in {MissionState.GENERATING, MissionState.PREVIEW_READY}:
            raise MediaMissionError("Assets may only be added while generating or reviewing.")
        if any(existing.asset_id == asset.asset_id for existing in self.assets):
            raise MediaMissionError(f"Duplicate asset id: {asset.asset_id}")
        self.assets.append(asset)
        self.approval = None
        if self.state is MissionState.PREVIEW_READY:
            self.state = MissionState.GENERATING

    def mark_preview_ready(self) -> str:
        self._require_state(MissionState.GENERATING)
        missing = {AssetKind.AUDIO, AssetKind.VIDEO} - {asset.kind for asset in self.assets}
        if missing:
            raise MediaMissionError("Preview requires assets: " + ", ".join(sorted(kind.value for kind in missing)))
        self.state = MissionState.PREVIEW_READY
        return self.preview_digest()

    def preview_digest(self) -> str:
        payload = {
            "mission_id": self.mission_id,
            "title": self.title,
            "brief": self.brief,
            "destination": self.destination,
            "assets": [
                {
                    "asset_id": asset.asset_id,
                    "kind": asset.kind.value,
                    "uri": asset.uri,
                    "sha256": asset.sha256,
                    "bytes_size": asset.bytes_size,
                    "provenance": asset.provenance.canonical_payload(),
                }
                for asset in sorted(self.assets, key=lambda item: item.asset_id)
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def approve_publish(self, *, approved_by: str, confirmation: str) -> PublishApproval:
        self._require_state(MissionState.PREVIEW_READY)
        if confirmation != "PUBLISH":
            raise MediaMissionError("Publishing requires the exact confirmation PUBLISH.")
        if not approved_by.strip():
            raise MediaMissionError("The approving user identity is required.")
        self.approval = PublishApproval(approved_by, datetime.now(UTC), self.preview_digest(), confirmation)
        self.state = MissionState.APPROVED
        return self.approval

    def begin_publish(self) -> None:
        self._require_state(MissionState.APPROVED)
        if self.approval is None:
            raise MediaMissionError("Publish approval is missing.")
        if self.preview_digest() != self.approval.preview_digest:
            self.approval = None
            self.state = MissionState.PREVIEW_READY
            raise MediaMissionError("Preview changed after approval; fresh approval is required.")
        self.state = MissionState.PUBLISHING

    def mark_published(self, url: str) -> None:
        self._require_state(MissionState.PUBLISHING)
        if not url.startswith(("https://", "http://")):
            raise MediaMissionError("A valid published URL is required.")
        self.published_url = url
        self.state = MissionState.PUBLISHED

    def fail(self, reason: str) -> None:
        if self.state in {MissionState.PUBLISHED, MissionState.CANCELLED}:
            raise MediaMissionError(f"Cannot fail a mission in state {self.state.value}.")
        self.failure_reason = reason.strip() or "unspecified failure"
        self.state = MissionState.FAILED

    def cancel(self) -> None:
        if self.state is MissionState.PUBLISHED:
            raise MediaMissionError("A published mission cannot be cancelled.")
        self.state = MissionState.CANCELLED

    def _require_state(self, expected: MissionState) -> None:
        if self.state is not expected:
            raise MediaMissionError(f"Expected mission state {expected.value!r}, found {self.state.value!r}.")
