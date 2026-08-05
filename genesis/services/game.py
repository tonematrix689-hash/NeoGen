"""Persistent avatars, Coins of the Dead ledger, forge, and marketplace services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from .events import EventBus
from .storage import SQLiteStore, StorageError


class GameError(RuntimeError):
    """Raised when an avatar or economy operation is invalid."""


@dataclass(frozen=True, slots=True)
class Avatar:
    id: str
    user_id: str
    name: str
    appearance: dict[str, Any]
    level: int
    created_at: datetime
    updated_at: datetime


class GameService:
    avatar_ns = "game.avatars"
    inventory_ns = "game.inventory"
    wallet_ns = "game.wallets"
    ledger_ns = "game.ledger"
    listing_ns = "game.marketplace"
    forge_ns = "game.forge_avatars"
    currency_code = "COTD"
    coins_per_aud = 100
    max_rarity = 1_000
    forge_layers = ("bones", "muscle", "skin", "armor", "weapons", "accessories", "appendages")
    power_thresholds = (10, 25, 50, 100, 250, 500, 750, 1_000)

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()
        self._economy_lock = RLock()

    def get_or_create_avatar(self, user_id: str, *, name: str = "Genesis") -> Avatar:
        key = self._avatar_key(user_id)
        try:
            return self._avatar(self._store.get(self.avatar_ns, key).value)
        except StorageError:
            now = datetime.now(timezone.utc)
            avatar = Avatar(f"avatar:{uuid4()}", user_id, name.strip() or "Genesis", {}, 1, now, now)
            self._store.put(self.avatar_ns, key, self._avatar_payload(avatar))
            self._events.publish("AvatarCreated", source="neogen.game", user_id=user_id, payload={"avatar_id": avatar.id})
            self.ensure_wallet(user_id, opening_balance=1000)
            return avatar

    def update_avatar(self, user_id: str, *, name: str | None = None, appearance: dict[str, Any] | None = None) -> Avatar:
        current = self.get_or_create_avatar(user_id)
        updated = Avatar(
            current.id,
            current.user_id,
            (name.strip() if name is not None else current.name) or current.name,
            dict(appearance if appearance is not None else current.appearance),
            current.level,
            current.created_at,
            datetime.now(timezone.utc),
        )
        record = self._store.get(self.avatar_ns, self._avatar_key(user_id))
        self._store.put(self.avatar_ns, self._avatar_key(user_id), self._avatar_payload(updated), expected_version=record.version)
        return updated

    def inventory(self, user_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(record.value for record in self._store.list(self.inventory_ns, prefix=f"{user_id}:"))

    def grant_item(self, user_id: str, *, item_type: str, name: str, rarity: int = 1, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if rarity < 1 or rarity > self.max_rarity:
            raise GameError("rarity must be between 1 and 1000")
        item = {
            "id": f"item:{uuid4()}", "user_id": user_id, "item_type": item_type,
            "name": name, "rarity": rarity, "metadata": dict(metadata or {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store.put(self.inventory_ns, f"{user_id}:{item['id']}", item)
        return item

    def ensure_wallet(self, user_id: str, *, opening_balance: int = 0) -> dict[str, Any]:
        try:
            return self._store.get(self.wallet_ns, user_id).value
        except StorageError:
            wallet = {"user_id": user_id, "currency": self.currency_code, "balance": max(0, int(opening_balance)), "updated_at": datetime.now(timezone.utc).isoformat()}
            self._store.put(self.wallet_ns, user_id, wallet)
            if wallet["balance"]:
                self._ledger(user_id, wallet["balance"], "opening_balance", None)
            return wallet

    def wallet(self, user_id: str) -> dict[str, Any]:
        return self.ensure_wallet(user_id)

    def coin_terms(self) -> dict[str, Any]:
        return {
            "code": self.currency_code,
            "name": "Coins of the Dead",
            "coins_per_aud": self.coins_per_aud,
            "reference_rate": "100 COTD = AUD 1.00",
            "mode": "development_closed_loop",
            "purchasing_enabled": False,
            "cash_redemption_enabled": False,
            "peer_transfer_enabled": False,
            "notice": "Development simulation only; no real-money payment, cash-out, or blockchain settlement is active.",
        }

    def quote_coins(self, aud_cents: int) -> dict[str, Any]:
        cents = int(aud_cents)
        if cents < 100 or cents > 1_000_000:
            raise GameError("AUD quote must be between $1.00 and $10,000.00")
        return {
            "aud_cents": cents,
            "coins": cents * self.coins_per_aud // 100,
            "currency": self.currency_code,
            "executable": False,
            "terms": self.coin_terms(),
        }

    def credit(self, user_id: str, amount: int, *, reason: str = "reward") -> dict[str, Any]:
        if amount <= 0:
            raise GameError("amount must be positive")
        return self._change_balance(user_id, amount, reason, None)

    def create_forge_avatar(self, user_id: str, *, name: str, prompt: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        avatar = {
            "id": f"forge:{uuid4()}",
            "user_id": user_id,
            "name": self._required_text(name, "name", 120),
            "origin_prompt": self._required_text(prompt, "prompt", 4_000),
            "rarity_level": 1,
            "layers": {},
            "powers": [],
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        self._store.put(self.forge_ns, avatar["id"], avatar)
        self._events.publish("ForgeAvatarCreated", source="neogen.game", user_id=user_id, payload={"avatar_id": avatar["id"]})
        return avatar

    def forge_avatars(self, user_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            record.value for record in self._store.list(self.forge_ns)
            if record.value.get("user_id") == user_id
        )

    def forge_avatar(self, user_id: str, avatar_id: str) -> dict[str, Any]:
        try:
            avatar = self._store.get(self.forge_ns, avatar_id).value
        except StorageError as exc:
            raise GameError("forge avatar not found") from exc
        if avatar.get("user_id") != user_id:
            raise GameError("forge avatar access denied")
        return avatar

    def layer_cost(self, rarity_level: int, layer_type: str) -> int:
        layer = layer_type.strip().lower()
        if layer not in self.forge_layers:
            raise GameError(f"layer_type must be one of: {', '.join(self.forge_layers)}")
        rarity = int(rarity_level)
        if rarity < 1 or rarity > self.max_rarity:
            raise GameError("rarity_level must be between 1 and 1000")
        return 25 + rarity * 5 + self.forge_layers.index(layer) * 10

    def add_forge_layer(self, user_id: str, avatar_id: str, *, layer_type: str, design_prompt: str, abilities: tuple[str, ...] = ()) -> dict[str, Any]:
        layer = layer_type.strip().lower()
        clean_prompt = self._required_text(design_prompt, "design_prompt", 8_000)
        clean_abilities = tuple(dict.fromkeys(self._required_text(item, "ability", 120) for item in abilities[:8]))
        with self._economy_lock:
            avatar = dict(self.forge_avatar(user_id, avatar_id))
            cost = self.layer_cost(int(avatar["rarity_level"]), layer)
            self._change_balance(user_id, -cost, "forge_layer", avatar_id)
            record = self._store.get(self.forge_ns, avatar_id)
            layers = dict(avatar.get("layers", {}))
            layers[layer] = {
                "type": layer, "design_prompt": clean_prompt, "abilities": clean_abilities,
                "rarity_level": int(avatar["rarity_level"]), "cost": cost,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            avatar.update({"layers": layers, "status": "forging", "updated_at": datetime.now(timezone.utc).isoformat()})
            try:
                self._store.put(self.forge_ns, avatar_id, avatar, expected_version=record.version)
            except Exception:
                self._change_balance(user_id, cost, "forge_layer_recovery", avatar_id)
                raise
        self._events.publish("ForgeLayerAdded", source="neogen.game", user_id=user_id, payload={"avatar_id": avatar_id, "layer": layer, "cost": cost})
        return avatar

    def rarity_upgrade_cost(self, current_level: int) -> int:
        level = int(current_level)
        if level < 1 or level >= self.max_rarity:
            raise GameError("rarity is already at its maximum or invalid")
        return 50 + level * 10 + (level // 100) * 250

    def upgrade_forge_avatar(self, user_id: str, avatar_id: str) -> dict[str, Any]:
        with self._economy_lock:
            avatar = dict(self.forge_avatar(user_id, avatar_id))
            current = int(avatar["rarity_level"])
            cost = self.rarity_upgrade_cost(current)
            next_level = current + 1
            self._change_balance(user_id, -cost, "forge_rarity_upgrade", avatar_id)
            record = self._store.get(self.forge_ns, avatar_id)
            powers = list(avatar.get("powers", []))
            if next_level in self.power_thresholds:
                powers.append({"unlocked_at": next_level, "status": "awaiting_ai_design"})
            avatar.update({
                "rarity_level": next_level,
                "powers": powers,
                "status": "complete" if all(item in avatar.get("layers", {}) for item in ("bones", "muscle", "skin")) else "forging",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            try:
                self._store.put(self.forge_ns, avatar_id, avatar, expected_version=record.version)
            except Exception:
                self._change_balance(user_id, cost, "forge_upgrade_recovery", avatar_id)
                raise
        self._events.publish("ForgeRarityUpgraded", source="neogen.game", user_id=user_id, payload={"avatar_id": avatar_id, "rarity_level": next_level, "cost": cost})
        return avatar

    def listings(self, *, active_only: bool = True) -> tuple[dict[str, Any], ...]:
        items = [record.value for record in self._store.list(self.listing_ns)]
        if active_only:
            items = [item for item in items if item.get("status") == "active"]
        return tuple(sorted(items, key=lambda item: item["created_at"], reverse=True))

    def create_listing(self, seller_id: str, *, name: str, description: str, price: int, item: dict[str, Any]) -> dict[str, Any]:
        if price <= 0:
            raise GameError("price must be positive")
        listing = {
            "id": f"listing:{uuid4()}", "seller_id": seller_id, "buyer_id": None,
            "name": name, "description": description, "price": int(price), "item": dict(item),
            "status": "active", "created_at": datetime.now(timezone.utc).isoformat(), "sold_at": None,
        }
        self._store.put(self.listing_ns, listing["id"], listing)
        return listing

    def purchase(self, buyer_id: str, listing_id: str) -> dict[str, Any]:
        try:
            record = self._store.get(self.listing_ns, listing_id)
        except StorageError as exc:
            raise GameError("listing not found") from exc
        listing = dict(record.value)
        if listing.get("status") != "active":
            raise GameError("listing is not active")
        if listing["seller_id"] == buyer_id:
            raise GameError("seller cannot buy own listing")
        price = int(listing["price"])
        wallet = self.ensure_wallet(buyer_id)
        if int(wallet["balance"]) < price:
            raise GameError("insufficient COTD balance")
        self._change_balance(buyer_id, -price, "marketplace_purchase", listing_id)
        self._change_balance(listing["seller_id"], price, "marketplace_sale", listing_id)
        item = dict(listing["item"])
        self.grant_item(buyer_id, item_type=str(item.get("item_type", "marketplace")), name=str(item.get("name", listing["name"])), rarity=int(item.get("rarity", 1)), metadata=item)
        listing.update({"status": "sold", "buyer_id": buyer_id, "sold_at": datetime.now(timezone.utc).isoformat()})
        self._store.put(self.listing_ns, listing_id, listing, expected_version=record.version)
        return listing

    def transactions(self, user_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(record.value for record in self._store.list(self.ledger_ns, prefix=f"{user_id}:"))

    def stats(self) -> dict[str, int]:
        return {
            "avatars": len(self._store.list(self.avatar_ns)),
            "items": len(self._store.list(self.inventory_ns)),
            "wallets": len(self._store.list(self.wallet_ns)),
            "transactions": len(self._store.list(self.ledger_ns)),
            "listings": len(self._store.list(self.listing_ns)),
            "forge_avatars": len(self._store.list(self.forge_ns)),
        }

    def _change_balance(self, user_id: str, delta: int, reason: str, reference_id: str | None) -> dict[str, Any]:
        wallet = self.ensure_wallet(user_id)
        record = self._store.get(self.wallet_ns, user_id)
        balance = int(wallet["balance"]) + int(delta)
        if balance < 0:
            raise GameError("insufficient COTD balance")
        updated = {"user_id": user_id, "currency": self.currency_code, "balance": balance, "updated_at": datetime.now(timezone.utc).isoformat()}
        self._store.put(self.wallet_ns, user_id, updated, expected_version=record.version)
        self._ledger(user_id, delta, reason, reference_id)
        return updated

    def _ledger(self, user_id: str, amount: int, reason: str, reference_id: str | None) -> dict[str, Any]:
        transaction = {
            "id": f"tx:{uuid4()}", "user_id": user_id, "amount": int(amount), "reason": reason,
            "reference_id": reference_id, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store.put(self.ledger_ns, f"{user_id}:{transaction['created_at']}:{transaction['id']}", transaction)
        return transaction

    @staticmethod
    def _required_text(value: str, field: str, max_length: int) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise GameError(f"{field} is required")
        if len(cleaned) > max_length:
            raise GameError(f"{field} exceeds {max_length} characters")
        return cleaned

    @staticmethod
    def _avatar_key(user_id: str) -> str:
        return user_id

    @staticmethod
    def _avatar_payload(value: Avatar) -> dict[str, Any]:
        return {"id": value.id, "user_id": value.user_id, "name": value.name, "appearance": value.appearance, "level": value.level, "created_at": value.created_at.isoformat(), "updated_at": value.updated_at.isoformat()}

    @staticmethod
    def _avatar(value: dict[str, Any]) -> Avatar:
        return Avatar(str(value["id"]), str(value["user_id"]), str(value["name"]), dict(value.get("appearance", {})), int(value.get("level", 1)), datetime.fromisoformat(str(value["created_at"])), datetime.fromisoformat(str(value["updated_at"])))
