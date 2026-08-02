"""Puter.js capability manifest and governed Tool Registry integration.

The browser bridge performs real Puter calls. This module declares the provider
inside the Python kernel so planning, permissions, health reporting, and agents
can reason about the available Puter capabilities consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .events import EventBus
from .permissions import PermissionManager, PermissionScope
from .tools import ToolDescriptor, ToolHealth, ToolRegistry, ToolRequest


@dataclass(frozen=True, slots=True)
class PuterCapability:
    id: str
    name: str
    description: str
    permissions: frozenset[PermissionScope]
    risk: float


PUTER_CAPABILITIES: tuple[PuterCapability, ...] = (
    PuterCapability(
        "puter.ai",
        "Puter AI",
        "Chat, model discovery, image understanding and generation, speech, and media AI.",
        frozenset({PermissionScope.USE_MODELS, PermissionScope.USE_NETWORK}),
        0.35,
    ),
    PuterCapability(
        "puter.auth",
        "Puter Authentication",
        "User-triggered Puter sign-in, sign-out, identity, and session access.",
        frozenset({PermissionScope.USE_NETWORK}),
        0.30,
    ),
    PuterCapability(
        "puter.fs",
        "Puter Cloud Filesystem",
        "Sandboxed cloud files, directories, uploads, copies, moves, and metadata.",
        frozenset({PermissionScope.READ_FILES, PermissionScope.WRITE_FILES, PermissionScope.USE_NETWORK}),
        0.55,
    ),
    PuterCapability(
        "puter.kv",
        "Puter Key-Value Storage",
        "Cloud-backed settings, counters, lightweight memory, and application state.",
        frozenset({PermissionScope.READ_MEMORY, PermissionScope.WRITE_MEMORY, PermissionScope.USE_NETWORK}),
        0.40,
    ),
    PuterCapability(
        "puter.apps",
        "Puter Application Management",
        "Discover, create, update, and remove Puter application records.",
        frozenset({PermissionScope.MANAGE_PLUGINS, PermissionScope.USE_NETWORK}),
        0.75,
    ),
    PuterCapability(
        "puter.hosting",
        "Puter Hosting",
        "Publish and manage static sites through Puter hosting.",
        frozenset({PermissionScope.DEPLOY, PermissionScope.USE_NETWORK}),
        0.90,
    ),
)


class PuterProviderError(RuntimeError):
    """Raised when the Puter provider is used outside its browser bridge."""


def register_puter_provider(
    registry: ToolRegistry,
    permissions: PermissionManager,
    events: EventBus,
) -> tuple[ToolDescriptor, ...]:
    """Register Puter capability groups with the governed Tool Registry.

    Tool requests are intentionally forwarded as browser execution envelopes.
    The web client consumes these envelopes with ``NeoGenPuterBridge``. This
    prevents the Python kernel from pretending it can directly access a browser
    user's Puter session.
    """

    del permissions  # Registry performs permission enforcement for each request.
    registered: list[ToolDescriptor] = []

    for capability in PUTER_CAPABILITIES:
        descriptor = ToolDescriptor(
            id=capability.id,
            name=capability.name,
            description=capability.description,
            capabilities=frozenset(
                {
                    capability.id,
                    "provider.puter",
                    "execution.browser",
                }
            ),
            required_permissions=capability.permissions,
            timeout_seconds=120.0,
            cost_score=0.25,
            platforms=frozenset({"browser", "web", "puter"}),
            health=ToolHealth.UNKNOWN,
        )

        def browser_envelope(request: ToolRequest, provider_id: str = capability.id) -> dict[str, Any]:
            envelope = {
                "provider": "puter",
                "provider_capability": provider_id,
                "operation": request.operation,
                "arguments": dict(request.arguments),
                "resource": request.resource,
                "correlation_id": request.correlation_id,
                "execution_target": "browser",
            }
            events.publish(
                "PuterBrowserExecutionRequested",
                source="neogen.puter",
                payload=envelope,
                correlation_id=request.correlation_id,
                user_id=request.subject_id,
            )
            return envelope

        registry.register(
            descriptor,
            browser_envelope,
            health_check=lambda: ToolHealth.HEALTHY,
        )
        registered.append(registry.check_health(descriptor.id))

    events.publish(
        "PuterProviderRegistered",
        source="neogen.puter",
        payload={
            "capabilities": [descriptor.id for descriptor in registered],
            "execution_target": "browser",
        },
    )
    return tuple(registered)
