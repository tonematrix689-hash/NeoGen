"""Durable storage for governed media missions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any

from genesis.apps.afterlife.media import (
    AssetKind,
    MediaAsset,
    MediaMission,
    MissionState,
    ProvenanceRecord,
    PublishApproval,
)


class MediaStoreError(RuntimeError):
    """Raised when mission persistence fails validation."""


_SAFE_ID = re.compile(r"^[a-f0-9-]{36}$")


class MediaMissionStore:
    """Store mission manifests atomically with append-only JSONL audit events."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, mission: MediaMission, *, actor: str, event: str) -> Path:
        mission_dir = self._mission_dir(mission.mission_id)
        mission_dir.mkdir(parents=True, exist_ok=True)
        manifest = mission_dir / "mission.json"
        temporary = mission_dir / "mission.json.tmp"
        payload = self._to_payload(mission)
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, manifest)
        self._append_audit(mission_dir, actor=actor, event=event, state=mission.state.value)
        return manifest

    def load(self, mission_id: str) -> MediaMission:
        manifest = self._mission_dir(mission_id) / "mission.json"
        if not manifest.is_file():
            raise MediaStoreError(f"Mission does not exist: {mission_id}")
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MediaStoreError(f"Mission manifest is unreadable: {mission_id}") from exc
        return self._from_payload(payload)

    def audit_events(self, mission_id: str) -> list[dict[str, Any]]:
        audit = self._mission_dir(mission_id) / "audit.jsonl"
        if not audit.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in audit.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def _mission_dir(self, mission_id: str) -> Path:
        if not _SAFE_ID.fullmatch(mission_id):
            raise MediaStoreError("Mission id is invalid.")
        path = (self.root / mission_id).resolve()
        if self.root not in path.parents:
            raise MediaStoreError("Mission path escaped the store root.")
        return path

    def _append_audit(self, mission_dir: Path, *, actor: str, event: str, state: str) -> None:
        if not actor.strip() or not event.strip():
            raise MediaStoreError("Audit actor and event are required.")
        record = {
            "at": datetime.now(UTC).isoformat(),
            "actor": actor,
            "event": event,
            "state": state,
        }
        with (mission_dir / "audit.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    @staticmethod
    def _to_payload(mission: MediaMission) -> dict[str, Any]:
        return {
            "mission_id": mission.mission_id,
            "title": mission.title,
            "brief": mission.brief,
            "destination": mission.destination,
            "state": mission.state.value,
            "published_url": mission.published_url,
            "failure_reason": mission.failure_reason,
            "approval": None if mission.approval is None else {
                "approved_by": mission.approval.approved_by,
                "approved_at": mission.approval.approved_at.astimezone(UTC).isoformat(),
                "preview_digest": mission.approval.preview_digest,
                "confirmation": mission.approval.confirmation,
            },
            "assets": [
                {
                    "asset_id": asset.asset_id,
                    "kind": asset.kind.value,
                    "uri": asset.uri,
                    "sha256": asset.sha256,
                    "bytes_size": asset.bytes_size,
                    "provenance": asset.provenance.canonical_payload(),
                }
                for asset in mission.assets
            ],
        }

    @staticmethod
    def _from_payload(payload: dict[str, Any]) -> MediaMission:
        mission = MediaMission(
            title=str(payload["title"]),
            brief=str(payload["brief"]),
            destination=str(payload.get("destination", "youtube")),
            mission_id=str(payload["mission_id"]),
            state=MissionState(payload["state"]),
            published_url=payload.get("published_url"),
            failure_reason=payload.get("failure_reason"),
        )
        for item in payload.get("assets", []):
            source = item["provenance"]
            mission.assets.append(MediaAsset(
                asset_id=str(item["asset_id"]),
                kind=AssetKind(item["kind"]),
                uri=str(item["uri"]),
                sha256=str(item["sha256"]),
                bytes_size=int(item["bytes_size"]),
                provenance=ProvenanceRecord(
                    provider=str(source["provider"]),
                    model=str(source["model"]),
                    prompt=str(source["prompt"]),
                    created_at=datetime.fromisoformat(source["created_at"]),
                    source_uris=tuple(source.get("source_uris", [])),
                    licence=str(source.get("licence", "unspecified")),
                    user_supplied=bool(source.get("user_supplied", False)),
                ),
            ))
        approval = payload.get("approval")
        if approval:
            mission.approval = PublishApproval(
                approved_by=str(approval["approved_by"]),
                approved_at=datetime.fromisoformat(approval["approved_at"]),
                preview_digest=str(approval["preview_digest"]),
                confirmation=str(approval["confirmation"]),
            )
        return mission
