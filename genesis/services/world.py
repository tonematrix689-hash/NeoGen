"""Persistent procedural-world preview and expedition service for NeoGen."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .events import EventBus
from .storage import SQLiteStore, StorageError


class WorldError(RuntimeError):
    """Raised when a world action is invalid."""


class WorldService:
    profile_namespace = "world.profiles"
    expedition_namespace = "world.expeditions"

    REGIONS: tuple[dict[str, Any], ...] = (
        {
            "id": "obsidian-reach",
            "name": "Obsidian Reach",
            "threat": 12,
            "minimum_level": 1,
            "description": "A resource-rich frontier shaped by unstable machine weather.",
            "base_reward": 90,
        },
        {
            "id": "genesis-vault",
            "name": "Genesis Vault",
            "threat": 28,
            "minimum_level": 10,
            "description": "Ancient architecture containing dormant synthetic intelligences.",
            "base_reward": 260,
        },
        {
            "id": "neural-wilds",
            "name": "Neural Wilds",
            "threat": 6,
            "minimum_level": 1,
            "description": "An adaptive habitat where digital companions emerge and evolve.",
            "base_reward": 55,
        },
    )

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()

    def regions(self) -> tuple[dict[str, Any], ...]:
        return self.REGIONS

    def profile(self, user_id: str) -> dict[str, Any]:
        try:
            value = dict(self._store.get(self.profile_namespace, user_id).value)
        except StorageError:
            value = {
                "user_id": user_id,
                "world_level": 1,
                "experience": 0,
                "essence": 0,
                "expeditions_completed": 0,
                "regions_discovered": ["obsidian-reach", "neural-wilds"],
                "legacy_score": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._store.put(self.profile_namespace, user_id, value)
        return value

    def expeditions(self, user_id: str) -> tuple[dict[str, Any], ...]:
        records = self._store.list(self.expedition_namespace, prefix=f"{user_id}:")
        return tuple(sorted((dict(r.value) for r in records), key=lambda x: str(x["created_at"]), reverse=True))

    def begin_expedition(self, user_id: str, region_id: str, *, avatar_level: int = 1) -> dict[str, Any]:
        region = next((item for item in self.REGIONS if item["id"] == region_id), None)
        if region is None:
            raise WorldError("Unknown region")
        if avatar_level < int(region["minimum_level"]):
            raise WorldError(f"{region['name']} requires avatar level {region['minimum_level']}")

        profile = self.profile(user_id)
        seed_text = f"{user_id}:{region_id}:{profile['expeditions_completed']}:{datetime.now(timezone.utc).date()}"
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        success_chance = max(0.25, min(0.92, 0.72 + avatar_level * 0.015 - int(region["threat"]) * 0.012))
        success = rng.random() <= success_chance
        reward = int(region["base_reward"] * (0.75 + rng.random() * 0.75)) if success else 0
        essence = rng.randint(3, max(4, int(region["threat"]))) if success else rng.randint(0, 2)
        experience = int(region["threat"]) * (8 if success else 2)
        discoveries = [
            "adaptive alloy fragment",
            "memory echo",
            "companion signal",
            "legacy coordinate",
            "procedural relic",
        ]
        discovery = rng.choice(discoveries) if success else "no stable discovery"

        expedition_id = f"{user_id}:{uuid4()}"
        result = {
            "id": expedition_id,
            "user_id": user_id,
            "region_id": region_id,
            "region_name": region["name"],
            "success": success,
            "reward_acoin": reward,
            "essence": essence,
            "experience": experience,
            "discovery": discovery,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store.put(self.expedition_namespace, expedition_id, result)

        profile["experience"] = int(profile.get("experience", 0)) + experience
        profile["essence"] = int(profile.get("essence", 0)) + essence
        profile["expeditions_completed"] = int(profile.get("expeditions_completed", 0)) + 1
        profile["world_level"] = 1 + int(profile["experience"]) // 500
        profile["legacy_score"] = int(profile.get("legacy_score", 0)) + experience + essence * 5
        discovered = set(profile.get("regions_discovered", []))
        discovered.add(region_id)
        profile["regions_discovered"] = sorted(discovered)
        profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._store.put(self.profile_namespace, user_id, profile)
        self._events.publish(
            "ExpeditionCompleted",
            source="neogen.world",
            user_id=user_id,
            payload=result,
        )
        return {"result": result, "profile": profile}

    def stats(self) -> dict[str, int]:
        return {
            "regions": len(self.REGIONS),
            "profiles": len(self._store.list(self.profile_namespace)),
            "expeditions": len(self._store.list(self.expedition_namespace)),
        }
