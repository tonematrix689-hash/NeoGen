"""Tests for governed Afterlife media missions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import unittest

from genesis.apps.afterlife.media import (
    AssetKind,
    MediaAsset,
    MediaMission,
    MediaMissionError,
    MissionState,
    ProvenanceRecord,
)


class MediaMissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provenance = ProvenanceRecord(
            provider="local-test",
            model="fixture-v1",
            prompt="Create a neon Afterlife scene",
            created_at=datetime(2026, 8, 3, 9, 30, tzinfo=UTC),
            licence="test-only",
        )

    def asset(self, kind: AssetKind, name: str, content: bytes) -> MediaAsset:
        return MediaAsset.from_bytes(
            kind=kind,
            uri=f"mission://assets/{name}",
            content=content,
            provenance=self.provenance,
        )

    def ready_mission(self) -> MediaMission:
        mission = MediaMission(title="Neon Legacy", brief="Music video for the Afterlife universe")
        mission.begin_generation()
        mission.add_asset(self.asset(AssetKind.AUDIO, "soundtrack.wav", b"audio-fixture"))
        mission.add_asset(self.asset(AssetKind.VIDEO, "preview.mp4", b"video-fixture"))
        mission.mark_preview_ready()
        return mission

    def test_asset_hash_uses_sha256(self) -> None:
        asset = self.asset(AssetKind.AUDIO, "track.wav", b"known-content")
        self.assertEqual(asset.sha256, hashlib.sha256(b"known-content").hexdigest())
        self.assertEqual(asset.bytes_size, len(b"known-content"))

    def test_preview_requires_audio_and_video(self) -> None:
        mission = MediaMission(title="Incomplete", brief="Missing video")
        mission.begin_generation()
        mission.add_asset(self.asset(AssetKind.AUDIO, "track.wav", b"audio"))

        with self.assertRaisesRegex(MediaMissionError, "video"):
            mission.mark_preview_ready()

        self.assertEqual(mission.state, MissionState.GENERATING)

    def test_preview_digest_is_stable(self) -> None:
        mission = self.ready_mission()
        self.assertEqual(mission.preview_digest(), mission.preview_digest())
        self.assertEqual(len(mission.preview_digest()), 64)

    def test_publish_requires_exact_confirmation(self) -> None:
        mission = self.ready_mission()

        for invalid in ("publish", "Publish", "YES", "PUBLISH "):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(MediaMissionError, "exact confirmation"):
                    mission.approve_publish(approved_by="founder", confirmation=invalid)

        self.assertEqual(mission.state, MissionState.PREVIEW_READY)
        self.assertIsNone(mission.approval)

    def test_approved_mission_can_publish(self) -> None:
        mission = self.ready_mission()
        approval = mission.approve_publish(approved_by="founder", confirmation="PUBLISH")

        self.assertEqual(approval.preview_digest, mission.preview_digest())
        self.assertEqual(mission.state, MissionState.APPROVED)

        mission.begin_publish()
        self.assertEqual(mission.state, MissionState.PUBLISHING)

        mission.mark_published("https://www.youtube.com/watch?v=test")
        self.assertEqual(mission.state, MissionState.PUBLISHED)
        self.assertEqual(mission.published_url, "https://www.youtube.com/watch?v=test")

    def test_changed_preview_invalidates_approval(self) -> None:
        mission = self.ready_mission()
        mission.approve_publish(approved_by="founder", confirmation="PUBLISH")
        original = mission.assets[0]
        mission.assets[0] = replace(original, sha256="0" * 64)

        with self.assertRaisesRegex(MediaMissionError, "fresh approval"):
            mission.begin_publish()

        self.assertEqual(mission.state, MissionState.PREVIEW_READY)
        self.assertIsNone(mission.approval)

    def test_invalid_state_transitions_fail_closed(self) -> None:
        mission = MediaMission(title="Guarded", brief="State validation")

        with self.assertRaises(MediaMissionError):
            mission.mark_preview_ready()
        with self.assertRaises(MediaMissionError):
            mission.begin_publish()
        with self.assertRaises(MediaMissionError):
            mission.mark_published("https://example.test/video")

        self.assertEqual(mission.state, MissionState.DRAFT)

    def test_published_mission_cannot_be_cancelled_or_failed(self) -> None:
        mission = self.ready_mission()
        mission.approve_publish(approved_by="founder", confirmation="PUBLISH")
        mission.begin_publish()
        mission.mark_published("https://example.test/video")

        with self.assertRaises(MediaMissionError):
            mission.cancel()
        with self.assertRaises(MediaMissionError):
            mission.fail("late failure")

        self.assertEqual(mission.state, MissionState.PUBLISHED)


if __name__ == "__main__":
    unittest.main()
