"""Persistent VERA conversations and governed AI response envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .events import EventBus
from .storage import SQLiteStore, StorageError
from .tools import ToolRegistry, ToolRequest


class ConversationError(RuntimeError):
    """Base conversation error."""


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any]


class ConversationService:
    """Persist VERA conversations and prepare governed Puter AI execution."""

    conversation_namespace = "vera.conversations"
    message_namespace = "vera.messages"

    def __init__(self, store: SQLiteStore, tools: ToolRegistry, events: EventBus | None = None) -> None:
        self._store = store
        self._tools = tools
        self._events = events or EventBus()

    def create(self, *, user_id: str, title: str = "New conversation") -> Conversation:
        user = self._required(user_id, "user_id")
        now = datetime.now(timezone.utc)
        conversation = Conversation(
            id=f"conversation:{uuid4()}",
            user_id=user,
            title=self._required(title, "title"),
            created_at=now,
            updated_at=now,
        )
        self._store.put(self.conversation_namespace, conversation.id, self._conversation_payload(conversation))
        self._events.publish(
            "ConversationCreated",
            source="neogen.vera",
            payload={"conversation_id": conversation.id, "title": conversation.title},
            user_id=user,
        )
        return conversation

    def get(self, conversation_id: str, *, user_id: str) -> Conversation:
        try:
            record = self._store.get(self.conversation_namespace, conversation_id).value
        except StorageError as exc:
            raise ConversationError(f"Unknown conversation: {conversation_id}") from exc
        conversation = self._conversation_from_payload(record)
        self._assert_owner(conversation, user_id)
        return conversation

    def list(self, *, user_id: str) -> tuple[Conversation, ...]:
        conversations = [
            self._conversation_from_payload(record.value)
            for record in self._store.list(self.conversation_namespace)
        ]
        return tuple(
            sorted(
                (item for item in conversations if item.user_id == user_id),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

    def rename(self, conversation_id: str, *, user_id: str, title: str) -> Conversation:
        conversation = self.get(conversation_id, user_id=user_id)
        updated = Conversation(
            id=conversation.id,
            user_id=conversation.user_id,
            title=self._required(title, "title"),
            created_at=conversation.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        current = self._store.get(self.conversation_namespace, conversation.id)
        self._store.put(
            self.conversation_namespace,
            conversation.id,
            self._conversation_payload(updated),
            expected_version=current.version,
        )
        self._events.publish(
            "ConversationRenamed",
            source="neogen.vera",
            payload={"conversation_id": conversation.id, "title": updated.title},
            user_id=user_id,
        )
        return updated

    def delete(self, conversation_id: str, *, user_id: str) -> Conversation:
        conversation = self.get(conversation_id, user_id=user_id)
        prefix = f"{conversation_id}:"
        while records := self._store.list(self.message_namespace, prefix=prefix):
            for record in records:
                self._store.delete(self.message_namespace, record.key)
        self._store.delete(self.conversation_namespace, conversation.id)
        self._events.publish(
            "ConversationDeleted",
            source="neogen.vera",
            payload={"conversation_id": conversation.id},
            user_id=user_id,
        )
        return conversation

    def messages(self, conversation_id: str, *, user_id: str) -> tuple[Message, ...]:
        self.get(conversation_id, user_id=user_id)
        prefix = f"{conversation_id}:"
        messages = [
            self._message_from_payload(record.value)
            for record in self._store.list(self.message_namespace, prefix=prefix)
        ]
        return tuple(sorted(messages, key=lambda item: item.created_at))

    def add_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        conversation = self.get(conversation_id, user_id=user_id)
        normalized_role = self._required(role, "role").lower()
        if normalized_role not in {"system", "user", "assistant", "tool"}:
            raise ConversationError(f"Unsupported message role: {normalized_role}")
        now = datetime.now(timezone.utc)
        message = Message(
            id=f"message:{uuid4()}",
            conversation_id=conversation_id,
            role=normalized_role,
            content=self._required(content, "content"),
            created_at=now,
            metadata=dict(metadata or {}),
        )
        key = f"{conversation_id}:{now.timestamp():020.6f}:{message.id}"
        self._store.put(self.message_namespace, key, self._message_payload(message))
        updated = Conversation(
            id=conversation.id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=now,
        )
        current = self._store.get(self.conversation_namespace, conversation.id)
        self._store.put(
            self.conversation_namespace,
            conversation.id,
            self._conversation_payload(updated),
            expected_version=current.version,
        )
        self._events.publish(
            "ConversationMessageAdded",
            source="neogen.vera",
            payload={
                "conversation_id": conversation_id,
                "message_id": message.id,
                "role": message.role,
            },
            user_id=user_id,
        )
        return message

    def request_ai_response(
        self,
        *,
        conversation_id: str,
        user_id: str,
        prompt: str,
        resource: str = "workspace:neogen",
        model: str | None = None,
    ) -> dict[str, Any]:
        user_message = self.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=prompt,
        )
        history = [
            {"role": item.role, "content": item.content}
            for item in self.messages(conversation_id, user_id=user_id)
            if item.role in {"system", "user", "assistant"}
        ]
        arguments: dict[str, Any] = {"messages": history}
        if model:
            arguments["model"] = model
        result = self._tools.execute(
            ToolRequest(
                subject_id=user_id,
                tool_id="puter.ai",
                operation="ai.chat",
                arguments=arguments,
                resource=resource,
                correlation_id=conversation_id,
            )
        )
        return {
            "conversation_id": conversation_id,
            "user_message": user_message,
            "execution": result,
            "status": "browser_execution_required",
        }

    def record_ai_response(
        self,
        *,
        conversation_id: str,
        user_id: str,
        content: str,
        provider: str = "puter",
        model: str | None = None,
    ) -> Message:
        metadata = {"provider": provider}
        if model:
            metadata["model"] = model
        return self.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=content,
            metadata=metadata,
        )

    def stats(self) -> dict[str, int]:
        return {
            "conversations": len(self._store.list(self.conversation_namespace)),
            "messages": len(self._store.list(self.message_namespace)),
        }

    @staticmethod
    def _assert_owner(conversation: Conversation, user_id: str) -> None:
        if conversation.user_id != user_id:
            raise ConversationError("Conversation access denied")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ConversationError(f"{field} is required")
        return cleaned

    @staticmethod
    def _conversation_payload(value: Conversation) -> dict[str, Any]:
        return {
            "id": value.id,
            "user_id": value.user_id,
            "title": value.title,
            "created_at": value.created_at.isoformat(),
            "updated_at": value.updated_at.isoformat(),
        }

    @staticmethod
    def _conversation_from_payload(value: dict[str, Any]) -> Conversation:
        return Conversation(
            id=str(value["id"]),
            user_id=str(value["user_id"]),
            title=str(value["title"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
        )

    @staticmethod
    def _message_payload(value: Message) -> dict[str, Any]:
        return {
            "id": value.id,
            "conversation_id": value.conversation_id,
            "role": value.role,
            "content": value.content,
            "created_at": value.created_at.isoformat(),
            "metadata": value.metadata,
        }

    @staticmethod
    def _message_from_payload(value: dict[str, Any]) -> Message:
        return Message(
            id=str(value["id"]),
            conversation_id=str(value["conversation_id"]),
            role=str(value["role"]),
            content=str(value["content"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            metadata=dict(value.get("metadata", {})),
        )
