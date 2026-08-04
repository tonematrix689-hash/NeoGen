"""Dependency-free ACoin double-entry ledger service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from uuid import uuid4

from .events import EventBus
from .storage import SQLiteStore, StorageError


class ACoinError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LedgerAccount:
    id: str
    owner_id: str
    asset: str
    kind: str
    created_at: str


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: str
    transaction_id: str
    account_id: str
    amount: str
    asset: str
    created_at: str


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    id: str
    reference: str
    description: str
    entries: tuple[LedgerEntry, ...]
    metadata: dict[str, Any]
    created_at: str


class ACoinService:
    account_namespace = "acoin.accounts"
    transaction_namespace = "acoin.transactions"
    entry_namespace = "acoin.entries"
    wallet_namespace = "acoin.wallets"
    ASSETS = ("NEO", "ESSENCE")

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()
        self._ensure_system_accounts()

    def wallet(self, owner_id: str) -> dict[str, Any]:
        owner = self._required(owner_id, "owner_id")
        accounts = {
            asset: self._get_or_create_account(owner, asset, "wallet")
            for asset in self.ASSETS
        }
        value = {
            "owner_id": owner,
            "accounts": {asset: account.id for asset, account in accounts.items()},
            "balances": {asset: self.balance(account.id) for asset, account in accounts.items()},
            "updated_at": self._now(),
        }
        self._store.put(self.wallet_namespace, owner, value)
        return value

    def balance(self, account_id: str) -> str:
        total = Decimal("0")
        for record in self._store.list(self.entry_namespace):
            value = record.value
            if value.get("account_id") == account_id:
                total += Decimal(str(value["amount"]))
        return self._format(total)

    def reward(
        self,
        owner_id: str,
        *,
        neo: Decimal | int | str = 0,
        essence: Decimal | int | str = 0,
        reason: str = "reward",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[LedgerTransaction, ...]:
        results: list[LedgerTransaction] = []
        for asset, raw_amount in (("NEO", neo), ("ESSENCE", essence)):
            amount = self._amount(raw_amount)
            if amount <= 0:
                continue
            source = self._get_or_create_account("system:rewards", asset, "system")
            target = self._get_or_create_account(owner_id, asset, "wallet")
            results.append(
                self.transfer(
                    source.id,
                    target.id,
                    amount,
                    description=reason,
                    reference=f"reward:{uuid4()}",
                    metadata=metadata,
                )
            )
        return tuple(results)

    def transfer(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: Decimal | int | str,
        *,
        description: str,
        reference: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LedgerTransaction:
        value = self._amount(amount)
        if value <= 0:
            raise ACoinError("amount must be greater than zero")
        source = self.account(from_account_id)
        target = self.account(to_account_id)
        if source.asset != target.asset:
            raise ACoinError("accounts must use the same asset")
        if source.id == target.id:
            raise ACoinError("source and destination must differ")
        if source.kind != "system" and Decimal(self.balance(source.id)) < value:
            raise ACoinError("insufficient balance")
        return self.post(
            reference=reference or f"transfer:{uuid4()}",
            description=description,
            postings=((source.id, -value), (target.id, value)),
            metadata=metadata,
        )

    def marketplace_settlement(
        self,
        *,
        buyer_id: str,
        seller_id: str,
        price: Decimal | int | str,
        listing_id: str,
        fee_rate: Decimal | int | str = "0.025",
    ) -> LedgerTransaction:
        amount = self._amount(price)
        rate = self._amount(fee_rate)
        if rate < 0 or rate >= 1:
            raise ACoinError("fee_rate must be between 0 and 1")
        buyer = self._get_or_create_account(buyer_id, "NEO", "wallet")
        seller = self._get_or_create_account(seller_id, "NEO", "wallet")
        treasury = self._get_or_create_account("system:treasury", "NEO", "system")
        if Decimal(self.balance(buyer.id)) < amount:
            raise ACoinError("insufficient balance")
        fee = (amount * rate).quantize(Decimal("0.00000001"))
        seller_amount = amount - fee
        return self.post(
            reference=f"marketplace:{listing_id}",
            description="Marketplace settlement",
            postings=((buyer.id, -amount), (seller.id, seller_amount), (treasury.id, fee)),
            metadata={
                "listing_id": listing_id,
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "fee_rate": self._format(rate),
            },
        )

    def post(
        self,
        *,
        reference: str,
        description: str,
        postings: Iterable[tuple[str, Decimal | int | str]],
        metadata: dict[str, Any] | None = None,
    ) -> LedgerTransaction:
        normalized: list[tuple[LedgerAccount, Decimal]] = []
        assets: set[str] = set()
        total = Decimal("0")
        for account_id, raw_amount in postings:
            account = self.account(account_id)
            amount = self._amount(raw_amount, allow_negative=True)
            if amount == 0:
                raise ACoinError("postings cannot be zero")
            normalized.append((account, amount))
            assets.add(account.asset)
            total += amount
        if len(normalized) < 2:
            raise ACoinError("double-entry transaction requires at least two postings")
        if len(assets) != 1:
            raise ACoinError("all postings must use one asset")
        if total != 0:
            raise ACoinError(f"transaction is not balanced: {self._format(total)}")

        transaction_id = f"acoin:tx:{uuid4()}"
        created_at = self._now()
        entries: list[LedgerEntry] = []
        for account, amount in normalized:
            entry = LedgerEntry(
                id=f"acoin:entry:{uuid4()}",
                transaction_id=transaction_id,
                account_id=account.id,
                amount=self._format(amount),
                asset=account.asset,
                created_at=created_at,
            )
            self._store.put(self.entry_namespace, entry.id, self._entry_payload(entry))
            entries.append(entry)

        transaction = LedgerTransaction(
            id=transaction_id,
            reference=self._required(reference, "reference"),
            description=self._required(description, "description"),
            entries=tuple(entries),
            metadata=dict(metadata or {}),
            created_at=created_at,
        )
        self._store.put(
            self.transaction_namespace,
            transaction.id,
            self._transaction_payload(transaction),
        )
        self._events.publish(
            "ACoinTransactionPosted",
            source="neogen.acoin",
            payload={"transaction_id": transaction.id, "reference": transaction.reference},
        )
        return transaction

    def account(self, account_id: str) -> LedgerAccount:
        try:
            value = self._store.get(self.account_namespace, account_id).value
        except StorageError as exc:
            raise ACoinError(f"unknown account: {account_id}") from exc
        return LedgerAccount(
            id=str(value["id"]),
            owner_id=str(value["owner_id"]),
            asset=str(value["asset"]),
            kind=str(value["kind"]),
            created_at=str(value["created_at"]),
        )

    def accounts(self, *, owner_id: str | None = None) -> tuple[LedgerAccount, ...]:
        accounts: list[LedgerAccount] = []
        for record in self._store.list(self.account_namespace):
            value = record.value
            if owner_id is not None and value.get("owner_id") != owner_id:
                continue
            accounts.append(
                LedgerAccount(
                    id=str(value["id"]),
                    owner_id=str(value["owner_id"]),
                    asset=str(value["asset"]),
                    kind=str(value["kind"]),
                    created_at=str(value["created_at"]),
                )
            )
        return tuple(accounts)

    def transactions(self, *, owner_id: str | None = None, limit: int = 100) -> tuple[dict[str, Any], ...]:
        account_ids = None
        if owner_id is not None:
            account_ids = {account.id for account in self.accounts(owner_id=owner_id)}
        values: list[dict[str, Any]] = []
        for record in self._store.list(self.transaction_namespace):
            transaction = dict(record.value)
            if account_ids is None or any(
                entry.get("account_id") in account_ids
                for entry in transaction.get("entries", [])
            ):
                values.append(transaction)
        values.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return tuple(values[: max(1, limit)])

    def reconcile(self) -> dict[str, Any]:
        totals = {asset: Decimal("0") for asset in self.ASSETS}
        orphan_entries: list[str] = []
        for record in self._store.list(self.entry_namespace):
            value = record.value
            try:
                self.account(str(value["account_id"]))
            except ACoinError:
                orphan_entries.append(str(value["id"]))
            asset = str(value["asset"])
            totals[asset] = totals.get(asset, Decimal("0")) + Decimal(str(value["amount"]))
        imbalanced = {
            asset: self._format(total)
            for asset, total in totals.items()
            if total != 0
        }
        return {
            "balanced": not imbalanced and not orphan_entries,
            "asset_totals": {asset: self._format(total) for asset, total in totals.items()},
            "imbalanced_assets": imbalanced,
            "orphan_entries": orphan_entries,
            "checked_at": self._now(),
        }

    def audit_export(self) -> dict[str, Any]:
        return {
            "service": "ACoin",
            "version": 1,
            "generated_at": self._now(),
            "accounts": [self._account_payload(account) for account in self.accounts()],
            "transactions": list(self.transactions(limit=1_000_000)),
            "reconciliation": self.reconcile(),
        }

    def stats(self) -> dict[str, Any]:
        return {
            "accounts": len(self._store.list(self.account_namespace)),
            "transactions": len(self._store.list(self.transaction_namespace)),
            "entries": len(self._store.list(self.entry_namespace)),
            "reconciliation": self.reconcile(),
        }

    def _get_or_create_account(self, owner_id: str, asset: str, kind: str) -> LedgerAccount:
        owner = self._required(owner_id, "owner_id")
        normalized_asset = asset.upper()
        if normalized_asset not in self.ASSETS:
            raise ACoinError(f"unsupported asset: {normalized_asset}")
        account_id = f"acoin:account:{owner}:{normalized_asset.lower()}"
        try:
            return self.account(account_id)
        except ACoinError:
            account = LedgerAccount(
                id=account_id,
                owner_id=owner,
                asset=normalized_asset,
                kind=kind,
                created_at=self._now(),
            )
            self._store.put(self.account_namespace, account.id, self._account_payload(account))
            return account

    def _ensure_system_accounts(self) -> None:
        for owner in ("system:rewards", "system:treasury"):
            for asset in self.ASSETS:
                self._get_or_create_account(owner, asset, "system")

    @staticmethod
    def _amount(value: Decimal | int | str, *, allow_negative: bool = False) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ACoinError("invalid amount") from exc
        if not amount.is_finite():
            raise ACoinError("amount must be finite")
        if not allow_negative and amount < 0:
            raise ACoinError("amount cannot be negative")
        return amount.quantize(Decimal("0.00000001"))

    @staticmethod
    def _format(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.00000001")), "f")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ACoinError(f"{field} is required")
        return cleaned

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _account_payload(account: LedgerAccount) -> dict[str, Any]:
        return {
            "id": account.id,
            "owner_id": account.owner_id,
            "asset": account.asset,
            "kind": account.kind,
            "created_at": account.created_at,
        }

    @staticmethod
    def _entry_payload(entry: LedgerEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "transaction_id": entry.transaction_id,
            "account_id": entry.account_id,
            "amount": entry.amount,
            "asset": entry.asset,
            "created_at": entry.created_at,
        }

    @classmethod
    def _transaction_payload(cls, transaction: LedgerTransaction) -> dict[str, Any]:
        return {
            "id": transaction.id,
            "reference": transaction.reference,
            "description": transaction.description,
            "entries": [cls._entry_payload(entry) for entry in transaction.entries],
            "metadata": transaction.metadata,
            "created_at": transaction.created_at,
        }
