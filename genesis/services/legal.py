"""Versioned legal notices, deployment readiness, and user acceptance records."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .events import EventBus
from .storage import SQLiteStore, StorageError


class LegalError(RuntimeError):
    """Raised when a legal document or acceptance record is invalid."""


@dataclass(frozen=True, slots=True)
class LegalDocument:
    id: str
    title: str
    version: str
    effective_date: str
    url: str
    mandatory: bool


DOCUMENT_VERSION = "2026-08-05.1"
LEGAL_DOCUMENTS = (
    LegalDocument("terms", "Terms of Service", DOCUMENT_VERSION, "2026-08-05", "/legal.html#terms", True),
    LegalDocument("privacy", "Privacy Notice", DOCUMENT_VERSION, "2026-08-05", "/legal.html#privacy", True),
    LegalDocument("acceptable-use", "Acceptable Use Policy", DOCUMENT_VERSION, "2026-08-05", "/legal.html#acceptable-use", True),
    LegalDocument("ai-transparency", "AI Transparency Notice", DOCUMENT_VERSION, "2026-08-05", "/legal.html#ai-transparency", True),
    LegalDocument("subscriptions", "Subscriptions and Cancellations", DOCUMENT_VERSION, "2026-08-05", "/legal.html#subscriptions", False),
    LegalDocument("cookies", "Cookies and Local Storage", DOCUMENT_VERSION, "2026-08-05", "/legal.html#cookies", False),
    LegalDocument("accessibility", "Accessibility Statement", DOCUMENT_VERSION, "2026-08-05", "/legal.html#accessibility", False),
    LegalDocument("ip", "Intellectual Property and Takedown", DOCUMENT_VERSION, "2026-08-05", "/legal.html#ip", False),
    LegalDocument("security", "Security and Incident Reporting", DOCUMENT_VERSION, "2026-08-05", "/legal.html#security", False),
    LegalDocument("regional", "Regional Privacy Notices", DOCUMENT_VERSION, "2026-08-05", "/legal.html#regional", False),
)

OPERATOR_ENVIRONMENT = {
    "operator_name": "NEOGEN_LEGAL_OPERATOR_NAME",
    "registered_address": "NEOGEN_LEGAL_REGISTERED_ADDRESS",
    "governing_law": "NEOGEN_LEGAL_GOVERNING_LAW",
    "privacy_email": "NEOGEN_LEGAL_PRIVACY_EMAIL",
    "security_email": "NEOGEN_LEGAL_SECURITY_EMAIL",
    "support_email": "NEOGEN_LEGAL_SUPPORT_EMAIL",
    "payment_provider": "NEOGEN_LEGAL_PAYMENT_PROVIDER",
    "data_hosting_regions": "NEOGEN_LEGAL_DATA_HOSTING_REGIONS",
}

OPERATOR_DEFAULTS = {
    "operator_name": "AVDigital One",
}

PLATFORM_IDENTITY = {
    "product_name": "NeoGen",
    "ecosystem_name": "The Metasphere",
    "operating_model": "decentralized global digital ecosystem",
}


class LegalService:
    """Expose current notices and preserve auditable, version-bound acceptance."""

    acceptance_namespace = "legal.acceptance"

    def __init__(self, store: SQLiteStore, events: EventBus | None = None) -> None:
        self._store = store
        self._events = events or EventBus()
        self._documents = {document.id: document for document in LEGAL_DOCUMENTS}

    def catalog(self) -> tuple[LegalDocument, ...]:
        return tuple(self._documents.values())

    def public_configuration(self) -> dict[str, Any]:
        values = {
            field: os.environ.get(variable, "").strip() or OPERATOR_DEFAULTS.get(field, "")
            for field, variable in OPERATOR_ENVIRONMENT.items()
        }
        missing = [field for field, value in values.items() if not value]
        return {
            "operator": values,
            "identity": dict(PLATFORM_IDENTITY),
            "ready_for_public_commerce": not missing,
            "missing_required_fields": missing,
            "minimum_age": 18,
            "documents_version": DOCUMENT_VERSION,
        }

    def current_acceptance(self, user_id: str) -> dict[str, Any]:
        try:
            record = dict(self._store.get(self.acceptance_namespace, user_id).value)
        except StorageError:
            record = {}
        mandatory = {document.id: document.version for document in self.catalog() if document.mandatory}
        accepted = dict(record.get("documents", {}))
        return {
            "accepted": bool(record) and all(accepted.get(key) == version for key, version in mandatory.items()),
            "record": record or None,
            "required_documents": mandatory,
        }

    def accept(
        self,
        user_id: str,
        documents: Mapping[str, str],
        *,
        age_confirmed: bool,
        locale: str = "",
        source: str = "web",
    ) -> dict[str, Any]:
        if not age_confirmed:
            raise LegalError("You must confirm that you are at least 18 and legally able to accept the terms")
        required = {document.id: document.version for document in self.catalog() if document.mandatory}
        normalized = {str(key): str(value) for key, value in documents.items()}
        if any(normalized.get(key) != version for key, version in required.items()):
            raise LegalError("Acceptance must match every current mandatory document version")
        record = {
            "user_id": user_id,
            "documents": required,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "age_confirmed": True,
            "locale": locale.strip()[:64],
            "source": source.strip()[:64] or "web",
        }
        self._store.put(self.acceptance_namespace, user_id, record)
        self._events.publish(
            "LegalTermsAccepted",
            source="neogen.legal",
            payload={"user_id": user_id, "documents": required},
            user_id=user_id,
        )
        return self.current_acceptance(user_id)

    def stats(self) -> dict[str, int]:
        return {"documents": len(self._documents), "acceptances": len(self._store.list(self.acceptance_namespace))}
