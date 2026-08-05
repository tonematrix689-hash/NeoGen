"""Persistent identity, password authentication, and bearer sessions for NeoGen."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .events import EventBus, EventSeverity
from .storage import SQLiteStore, StorageError


class IdentityError(RuntimeError):
    """Base identity error."""


@dataclass(frozen=True, slots=True)
class User:
    id: str
    email: str
    display_name: str
    roles: tuple[str, ...]
    active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    user_id: str
    token: str
    created_at: datetime
    expires_at: datetime


class IdentityService:
    """Dependency-free persistent user and session management."""

    user_namespace = "identity.users"
    email_namespace = "identity.email_index"
    session_namespace = "identity.sessions"
    iterations = 310_000

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()

    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        roles: tuple[str, ...] = ("user",),
    ) -> User:
        normalized_email = self._normalize_email(email)
        self._validate_password(password)
        name = self._required(display_name, "display_name")
        try:
            self._store.get(self.email_namespace, normalized_email)
        except StorageError:
            pass
        else:
            raise IdentityError("Email is already registered")

        existing_users = self._store.list(self.user_namespace)
        assigned_roles = set(roles or ("user",))
        if not existing_users:
            assigned_roles.update({"user", "admin", "owner"})

        user_id = f"user:{uuid4()}"
        created_at = datetime.now(timezone.utc)
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.iterations)
        record = {
            "id": user_id,
            "email": normalized_email,
            "display_name": name,
            "roles": sorted(assigned_roles),
            "active": True,
            "created_at": created_at.isoformat(),
            "password": {
                "algorithm": "pbkdf2_sha256",
                "iterations": self.iterations,
                "salt": base64.b64encode(salt).decode("ascii"),
                "digest": base64.b64encode(digest).decode("ascii"),
            },
        }
        self._store.put(self.user_namespace, user_id, record)
        self._store.put(self.email_namespace, normalized_email, {"user_id": user_id})
        user = self._user_from_record(record)
        self._events.publish(
            "UserRegistered",
            source="neogen.identity",
            payload={"user_id": user.id, "email": user.email, "roles": list(user.roles)},
            user_id=user.id,
        )
        return user

    def authenticate(
        self,
        *,
        email: str,
        password: str,
        session_hours: int = 24,
    ) -> Session:
        normalized_email = self._normalize_email(email)
        if session_hours <= 0 or session_hours > 24 * 30:
            raise IdentityError("session_hours must be between 1 and 720")
        try:
            index = self._store.get(self.email_namespace, normalized_email).value
            record = self._store.get(self.user_namespace, str(index["user_id"])).value
        except (StorageError, KeyError) as exc:
            self._authentication_failed(normalized_email)
            raise IdentityError("Invalid email or password") from exc
        if not bool(record.get("active", False)) or not self._verify_password(password, record):
            self._authentication_failed(normalized_email)
            raise IdentityError("Invalid email or password")

        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(hours=session_hours)
        session_id = f"session:{uuid4()}"
        token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(token)
        self._store.put(
            self.session_namespace,
            token_hash,
            {
                "id": session_id,
                "user_id": str(record["id"]),
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )
        session = Session(session_id, str(record["id"]), token, created_at, expires_at)
        self._events.publish(
            "UserAuthenticated",
            source="neogen.identity",
            payload={"user_id": session.user_id, "session_id": session.id},
            user_id=session.user_id,
        )
        return session

    def resolve(self, token: str) -> User:
        cleaned = self._required(token, "token")
        try:
            session_record = self._store.get(self.session_namespace, self._token_hash(cleaned)).value
        except StorageError as exc:
            raise IdentityError("Invalid or expired session") from exc
        expires_at = datetime.fromisoformat(str(session_record["expires_at"]))
        if expires_at <= datetime.now(timezone.utc):
            try:
                self._store.delete(self.session_namespace, self._token_hash(cleaned))
            except StorageError:
                pass
            raise IdentityError("Invalid or expired session")
        return self.get_user(str(session_record["user_id"]))

    def logout(self, token: str) -> None:
        key = self._token_hash(self._required(token, "token"))
        try:
            session = self._store.delete(self.session_namespace, key)
        except StorageError as exc:
            raise IdentityError("Invalid session") from exc
        self._events.publish(
            "UserLoggedOut",
            source="neogen.identity",
            payload={"session_id": session.value.get("id")},
            user_id=session.value.get("user_id"),
        )

    def get_user(self, user_id: str) -> User:
        try:
            return self._user_from_record(self._store.get(self.user_namespace, user_id).value)
        except StorageError as exc:
            raise IdentityError(f"Unknown user: {user_id}") from exc

    def stats(self) -> dict[str, int]:
        return {
            "users": len(self._store.list(self.user_namespace)),
            "sessions": len(self._store.list(self.session_namespace)),
        }

    def _authentication_failed(self, email: str) -> None:
        self._events.publish(
            "AuthenticationFailed",
            source="neogen.identity",
            severity=EventSeverity.WARNING,
            payload={"email": email},
        )

    @classmethod
    def _verify_password(cls, password: str, record: dict[str, Any]) -> bool:
        try:
            password_record = record["password"]
            salt = base64.b64decode(password_record["salt"])
            expected = base64.b64decode(password_record["digest"])
            iterations = int(password_record["iterations"])
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityError("Stored password record is invalid") from exc
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_email(cls, email: str) -> str:
        value = cls._required(email, "email").lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise IdentityError("A valid email is required")
        return value

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 10:
            raise IdentityError("Password must be at least 10 characters")
        if len(password) > 512:
            raise IdentityError("Password is too long")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise IdentityError(f"{field} is required")
        return cleaned

    @staticmethod
    def _user_from_record(record: dict[str, Any]) -> User:
        return User(
            id=str(record["id"]),
            email=str(record["email"]),
            display_name=str(record["display_name"]),
            roles=tuple(str(role) for role in record.get("roles", ("user",))),
            active=bool(record.get("active", True)),
            created_at=datetime.fromisoformat(str(record["created_at"])),
        )
