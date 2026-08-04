"""Persistent avatar, inventory, ACoin wallet, and marketplace services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()

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
        if rarity < 1 or rarity > 100:
            raise GameError("rarity must be between 1 and 100")
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
            wallet = {"user_id": user_id, "balance": max(0, int(opening_balance)), "updated_at": datetime.now(timezone.utc).isoformat()}
            self._store.put(self.wallet_ns, user_id, wallet)
            if wallet["balance"]:
                self._ledger(user_id, wallet["balance"], "opening_balance", None)
            return wallet

    def wallet(self, user_id: str) -> dict[str, Any]:
        return self.ensure_wallet(user_id)

    def credit(self, user_id: str, amount: int, *, reason: str = "reward") -> dict[str, Any]:
        if amount <= 0:
            raise GameError("amount must be positive")
        return self._change_balance(user_id, amount, reason, None)

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
            raise GameError("insufficient ACoin balance")
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
        }

    def _change_balance(self, user_id: str, delta: int, reason: str, reference_id: str | None) -> dict[str, Any]:
        wallet = self.ensure_wallet(user_id)
        record = self._store.get(self.wallet_ns, user_id)
        balance = int(wallet["balance"]) + int(delta)
        if balance < 0:
            raise GameError("insufficient ACoin balance")
        updated = {"user_id": user_id, "balance": balance, "updated_at": datetime.now(timezone.utc).isoformat()}
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
    def _avatar_key(user_id: str) -> str:
        return user_id

    @staticmethod
    def _avatar_payload(value: Avatar) -> dict[str, Any]:
        return {"id": value.id, "user_id": value.user_id, "name": value.name, "appearance": value.appearance, "level": value.level, "created_at": value.created_at.isoformat(), "updated_at": value.updated_at.isoformat()}

    @staticmethod
    def _avatar(value: dict[str, Any]) -> Avatar:
        return Avatar(str(value["id"]), str(value["user_id"]), str(value["name"]), dict(value.get("appearance", {})), int(value.get("level", 1)), datetime.fromisoformat(str(value["created_at"])), datetime.fromisoformat(str(value["updated_at"])))
