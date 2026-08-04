"""Persistent Afterlife MVP domain service: avatar, inventory, ACoin wallet, marketplace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .events import EventBus
from .storage import SQLiteStore, StorageError


class AfterlifeError(RuntimeError):
    """Raised when an Afterlife domain operation is invalid."""


@dataclass(frozen=True, slots=True)
class Avatar:
    user_id: str
    name: str
    appearance: dict[str, Any]
    level: int
    experience: int
    updated_at: datetime


class AfterlifeService:
    avatar_ns = "afterlife.avatars"
    wallet_ns = "afterlife.wallets"
    transaction_ns = "afterlife.transactions"
    inventory_ns = "afterlife.inventory"
    listing_ns = "afterlife.marketplace"

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()

    def avatar(self, user_id: str) -> Avatar:
        try:
            value = self._store.get(self.avatar_ns, user_id).value
        except StorageError:
            return Avatar(user_id, "Unnamed", {}, 1, 0, datetime.now(timezone.utc))
        return Avatar(
            user_id=user_id,
            name=str(value.get("name", "Unnamed")),
            appearance=dict(value.get("appearance", {})),
            level=int(value.get("level", 1)),
            experience=int(value.get("experience", 0)),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
        )

    def save_avatar(self, user_id: str, *, name: str, appearance: dict[str, Any]) -> Avatar:
        current = self.avatar(user_id)
        result = Avatar(
            user_id=user_id,
            name=self._required(name, "name"),
            appearance=dict(appearance),
            level=current.level,
            experience=current.experience,
            updated_at=datetime.now(timezone.utc),
        )
        self._store.put(self.avatar_ns, user_id, {
            "name": result.name,
            "appearance": result.appearance,
            "level": result.level,
            "experience": result.experience,
            "updated_at": result.updated_at.isoformat(),
        })
        self._events.publish("AvatarSaved", source="afterlife", user_id=user_id, payload={"name": result.name})
        return result

    def wallet(self, user_id: str) -> dict[str, Any]:
        try:
            value = self._store.get(self.wallet_ns, user_id).value
        except StorageError:
            self._store.put(self.wallet_ns, user_id, {"balance": 1000})
            self._record_transaction(user_id, 1000, "Welcome grant")
            value = {"balance": 1000}
        return {"user_id": user_id, "balance": int(value.get("balance", 0)), "currency": "AC"}

    def transactions(self, user_id: str) -> tuple[dict[str, Any], ...]:
        items = [r.value for r in self._store.list(self.transaction_ns, prefix=f"{user_id}:")]
        return tuple(sorted(items, key=lambda x: str(x["created_at"])))

    def inventory(self, user_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(r.value for r in self._store.list(self.inventory_ns, prefix=f"{user_id}:"))

    def listings(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            r.value for r in self._store.list(self.listing_ns)
            if str(r.value.get("status", "active")) == "active"
        )

    def create_listing(
        self,
        user_id: str,
        *,
        name: str,
        description: str,
        price: int,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        if price <= 0:
            raise AfterlifeError("price must be greater than zero")
        listing_id = f"listing:{uuid4()}"
        listing = {
            "id": listing_id,
            "seller_id": user_id,
            "name": self._required(name, "name"),
            "description": str(description),
            "price": int(price),
            "item": dict(item),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store.put(self.listing_ns, listing_id, listing)
        self._events.publish("MarketplaceListingCreated", source="afterlife", user_id=user_id, payload={"listing_id": listing_id})
        return listing

    def purchase(self, buyer_id: str, listing_id: str) -> dict[str, Any]:
        try:
            record = self._store.get(self.listing_ns, listing_id)
        except StorageError as exc:
            raise AfterlifeError("Listing not found") from exc
        listing = dict(record.value)
        if listing.get("status") != "active":
            raise AfterlifeError("Listing is not active")
        if listing.get("seller_id") == buyer_id:
            raise AfterlifeError("You cannot buy your own listing")
        price = int(listing["price"])
        buyer = self.wallet(buyer_id)
        if buyer["balance"] < price:
            raise AfterlifeError("Insufficient ACoin balance")
        seller_id = str(listing["seller_id"])
        seller = self.wallet(seller_id)
        self._store.put(self.wallet_ns, buyer_id, {"balance": buyer["balance"] - price})
        self._store.put(self.wallet_ns, seller_id, {"balance": seller["balance"] + price})
        self._record_transaction(buyer_id, -price, f"Purchased {listing['name']}")
        self._record_transaction(seller_id, price, f"Sold {listing['name']}")
        inventory_id = f"{buyer_id}:{uuid4()}"
        item = dict(listing.get("item", {}))
        item.update({
            "id": inventory_id,
            "name": item.get("name") or listing["name"],
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "source_listing_id": listing_id,
        })
        self._store.put(self.inventory_ns, inventory_id, item)
        listing["status"] = "sold"
        listing["buyer_id"] = buyer_id
        listing["sold_at"] = datetime.now(timezone.utc).isoformat()
        self._store.put(self.listing_ns, listing_id, listing, expected_version=record.version)
        self._events.publish("MarketplacePurchaseCompleted", source="afterlife", user_id=buyer_id, payload={"listing_id": listing_id, "price": price})
        return {"listing": listing, "wallet": self.wallet(buyer_id), "item": item}

    def stats(self) -> dict[str, int]:
        return {
            "avatars": len(self._store.list(self.avatar_ns)),
            "wallets": len(self._store.list(self.wallet_ns)),
            "transactions": len(self._store.list(self.transaction_ns)),
            "inventory_items": len(self._store.list(self.inventory_ns)),
            "listings": len(self._store.list(self.listing_ns)),
        }

    def _record_transaction(self, user_id: str, amount: int, reason: str) -> None:
        transaction_id = f"{user_id}:{datetime.now(timezone.utc).timestamp():020.6f}:{uuid4()}"
        self._store.put(self.transaction_ns, transaction_id, {
            "id": transaction_id,
            "user_id": user_id,
            "amount": int(amount),
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise AfterlifeError(f"{field} is required")
        return cleaned
