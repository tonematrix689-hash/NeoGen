"""NeoGen capability policy, user roles, and risk classification.

The catalog describes what a capability means and how it should be governed.
Actual grants and approval requests remain the responsibility of
``PermissionManager`` so existing tool integrations stay compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Iterable


class RiskLevel(IntEnum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class UserRole(StrEnum):
    GUEST = "guest"
    USER = "user"
    POWER_USER = "power_user"
    DEVELOPER = "developer"
    ADMINISTRATOR = "administrator"
    ORGANIZATION_ADMIN = "organization_admin"


class CapabilityCategory(StrEnum):
    SYSTEM = "system"
    FILES = "files"
    TERMINAL = "terminal"
    DEVELOPMENT = "development"
    NETWORK = "network"
    BROWSER = "browser"
    AI = "ai"
    AUTOMATION = "automation"
    PRIVACY = "privacy"
    ECONOMY = "economy"
    GOVERNANCE = "governance"


@dataclass(frozen=True, slots=True)
class CapabilityPolicy:
    id: str
    title: str
    category: CapabilityCategory
    risk: RiskLevel
    purpose: str
    approval_required: bool
    unattended_allowed: bool = False
    reversible: bool = True
    audit_event: str = "CapabilityUsed"


class GovernanceCatalog:
    """Immutable product policy catalog for NeoGen capabilities."""

    ROLE_ORDER = {
        UserRole.GUEST: 0,
        UserRole.USER: 1,
        UserRole.POWER_USER: 2,
        UserRole.DEVELOPER: 3,
        UserRole.ADMINISTRATOR: 4,
        UserRole.ORGANIZATION_ADMIN: 5,
    }

    ROLE_MINIMUMS: dict[str, UserRole] = {
        "chat.use": UserRole.GUEST,
        "memory.read": UserRole.USER,
        "memory.write": UserRole.USER,
        "memory.delete": UserRole.USER,
        "workspace.search": UserRole.USER,
        "files.read": UserRole.USER,
        "files.create": UserRole.USER,
        "files.write": UserRole.USER,
        "files.delete": UserRole.POWER_USER,
        "files.execute": UserRole.POWER_USER,
        "terminal.execute": UserRole.POWER_USER,
        "terminal.background": UserRole.POWER_USER,
        "packages.install": UserRole.DEVELOPER,
        "development.project.create": UserRole.USER,
        "development.source.modify": UserRole.POWER_USER,
        "development.tests.run": UserRole.POWER_USER,
        "git.commit": UserRole.POWER_USER,
        "git.push": UserRole.DEVELOPER,
        "git.merge": UserRole.DEVELOPER,
        "software.release": UserRole.DEVELOPER,
        "network.internet": UserRole.USER,
        "network.download": UserRole.USER,
        "network.upload": UserRole.POWER_USER,
        "network.ssh": UserRole.DEVELOPER,
        "browser.open": UserRole.USER,
        "browser.automate": UserRole.POWER_USER,
        "browser.cookies": UserRole.POWER_USER,
        "automation.run": UserRole.POWER_USER,
        "automation.schedule": UserRole.POWER_USER,
        "automation.unattended": UserRole.DEVELOPER,
        "privacy.camera": UserRole.USER,
        "privacy.microphone": UserRole.USER,
        "privacy.screen_capture": UserRole.USER,
        "privacy.contacts": UserRole.USER,
        "privacy.calendar": UserRole.USER,
        "privacy.email": UserRole.USER,
        "system.settings.modify": UserRole.ADMINISTRATOR,
        "system.software.install": UserRole.ADMINISTRATOR,
        "system.registry.modify": UserRole.ADMINISTRATOR,
        "system.restart": UserRole.ADMINISTRATOR,
        "system.shutdown": UserRole.ADMINISTRATOR,
        "system.remote_execute": UserRole.ADMINISTRATOR,
        "economy.spend": UserRole.USER,
        "economy.trade": UserRole.USER,
        "governance.policy.manage": UserRole.ORGANIZATION_ADMIN,
    }

    def __init__(self) -> None:
        self._policies = {policy.id: policy for policy in self._default_policies()}

    def get(self, capability_id: str) -> CapabilityPolicy:
        try:
            return self._policies[capability_id]
        except KeyError as exc:
            raise KeyError(f"Unknown capability: {capability_id}") from exc

    def list(
        self,
        *,
        category: CapabilityCategory | None = None,
        maximum_risk: RiskLevel | None = None,
    ) -> tuple[CapabilityPolicy, ...]:
        policies = self._policies.values()
        result = [
            policy
            for policy in policies
            if (category is None or policy.category is category)
            and (maximum_risk is None or policy.risk <= maximum_risk)
        ]
        return tuple(sorted(result, key=lambda item: (item.category.value, item.risk, item.id)))

    def role_allows(self, roles: Iterable[str], capability_id: str) -> bool:
        required = self.ROLE_MINIMUMS.get(capability_id, UserRole.ORGANIZATION_ADMIN)
        resolved = []
        for role in roles:
            normalized = {
                "admin": UserRole.ADMINISTRATOR,
                "organization_admin": UserRole.ORGANIZATION_ADMIN,
            }.get(str(role), None)
            if normalized is None:
                try:
                    normalized = UserRole(str(role))
                except ValueError:
                    continue
            resolved.append(normalized)
        return any(self.ROLE_ORDER[role] >= self.ROLE_ORDER[required] for role in resolved)

    def decision_requirements(self, capability_id: str) -> dict[str, object]:
        policy = self.get(capability_id)
        return {
            "capability": policy.id,
            "risk_level": int(policy.risk),
            "risk_name": policy.risk.name.lower(),
            "approval_required": policy.approval_required,
            "unattended_allowed": policy.unattended_allowed,
            "reversible": policy.reversible,
            "audit_event": policy.audit_event,
            "minimum_role": self.ROLE_MINIMUMS.get(policy.id, UserRole.ORGANIZATION_ADMIN).value,
        }

    def snapshot(self) -> dict[str, object]:
        return {
            "risk_levels": {level.name.lower(): int(level) for level in RiskLevel},
            "roles": [role.value for role in UserRole],
            "categories": [category.value for category in CapabilityCategory],
            "capabilities": [self._as_dict(policy) for policy in self.list()],
            "controls": {
                "explicit_consent": True,
                "least_privilege": True,
                "visible_actions": True,
                "audit_required": True,
                "pause_and_stop": True,
                "memory_inspection": True,
                "memory_export_and_deletion": True,
                "hidden_persistence_prohibited": True,
                "unauthorized_replication_prohibited": True,
                "shutdown_resistance_prohibited": True,
            },
        }

    @staticmethod
    def _as_dict(policy: CapabilityPolicy) -> dict[str, object]:
        return {
            "id": policy.id,
            "title": policy.title,
            "category": policy.category.value,
            "risk_level": int(policy.risk),
            "risk_name": policy.risk.name.lower(),
            "purpose": policy.purpose,
            "approval_required": policy.approval_required,
            "unattended_allowed": policy.unattended_allowed,
            "reversible": policy.reversible,
            "audit_event": policy.audit_event,
            "minimum_role": GovernanceCatalog.ROLE_MINIMUMS.get(
                policy.id, UserRole.ORGANIZATION_ADMIN
            ).value,
        }

    @staticmethod
    def _default_policies() -> tuple[CapabilityPolicy, ...]:
        C = CapabilityPolicy
        return (
            C("chat.use", "Use conversation", CapabilityCategory.AI, RiskLevel.SAFE, "Hold natural-language conversations", False, True),
            C("memory.read", "Recall memory", CapabilityCategory.AI, RiskLevel.SAFE, "Retrieve approved memories", False, True),
            C("memory.write", "Store memory", CapabilityCategory.AI, RiskLevel.LOW, "Store user-approved durable context", True),
            C("memory.delete", "Delete memory", CapabilityCategory.AI, RiskLevel.MEDIUM, "Remove durable memory records", True),
            C("workspace.search", "Search workspace", CapabilityCategory.FILES, RiskLevel.SAFE, "Search approved workspace content", False, True),
            C("files.read", "Read files", CapabilityCategory.FILES, RiskLevel.LOW, "Read files inside approved workspaces", True, True),
            C("files.create", "Create files", CapabilityCategory.FILES, RiskLevel.LOW, "Create new workspace files", True),
            C("files.write", "Modify files", CapabilityCategory.FILES, RiskLevel.MEDIUM, "Modify existing project files", True),
            C("files.delete", "Delete files", CapabilityCategory.FILES, RiskLevel.HIGH, "Delete workspace files", True),
            C("files.execute", "Execute files", CapabilityCategory.FILES, RiskLevel.HIGH, "Execute approved files or scripts", True, False),
            C("terminal.execute", "Execute terminal commands", CapabilityCategory.TERMINAL, RiskLevel.HIGH, "Run commands in an approved workspace", True, False),
            C("terminal.background", "Run background process", CapabilityCategory.TERMINAL, RiskLevel.HIGH, "Run bounded long-lived processes", True, True),
            C("packages.install", "Install packages", CapabilityCategory.TERMINAL, RiskLevel.HIGH, "Install project or system packages", True, False),
            C("development.project.create", "Create projects", CapabilityCategory.DEVELOPMENT, RiskLevel.LOW, "Create project structures and templates", True),
            C("development.source.modify", "Modify source code", CapabilityCategory.DEVELOPMENT, RiskLevel.MEDIUM, "Edit application source code", True),
            C("development.tests.run", "Run tests", CapabilityCategory.DEVELOPMENT, RiskLevel.MEDIUM, "Execute approved test suites", True, True),
            C("git.commit", "Commit Git changes", CapabilityCategory.DEVELOPMENT, RiskLevel.MEDIUM, "Create a local Git commit", True),
            C("git.push", "Push Git changes", CapabilityCategory.NETWORK, RiskLevel.HIGH, "Publish commits to a remote", True, False),
            C("git.merge", "Merge branches", CapabilityCategory.DEVELOPMENT, RiskLevel.HIGH, "Merge branches or pull requests", True, False),
            C("software.release", "Release software", CapabilityCategory.DEVELOPMENT, RiskLevel.HIGH, "Publish a software release", True, False),
            C("network.internet", "Access internet", CapabilityCategory.NETWORK, RiskLevel.LOW, "Access public internet resources", True, True),
            C("network.download", "Download files", CapabilityCategory.NETWORK, RiskLevel.MEDIUM, "Download content into an approved workspace", True, True),
            C("network.upload", "Upload files", CapabilityCategory.NETWORK, RiskLevel.HIGH, "Upload user data to an external service", True, False),
            C("network.ssh", "Use SSH", CapabilityCategory.NETWORK, RiskLevel.HIGH, "Connect to an approved remote host", True, False),
            C("browser.open", "Open URLs", CapabilityCategory.BROWSER, RiskLevel.LOW, "Open user-selected web resources", True, True),
            C("browser.automate", "Automate browser", CapabilityCategory.BROWSER, RiskLevel.HIGH, "Interact with websites on the user's behalf", True, False),
            C("browser.cookies", "Access browser sessions", CapabilityCategory.BROWSER, RiskLevel.HIGH, "Use approved cookies or authenticated sessions", True, False),
            C("automation.run", "Run workflows", CapabilityCategory.AUTOMATION, RiskLevel.MEDIUM, "Run a bounded workflow", True, True),
            C("automation.schedule", "Schedule jobs", CapabilityCategory.AUTOMATION, RiskLevel.MEDIUM, "Create a scheduled bounded task", True, True),
            C("automation.unattended", "Run unattended", CapabilityCategory.AUTOMATION, RiskLevel.HIGH, "Run approved work without active interaction", True, True),
            C("privacy.camera", "Use camera", CapabilityCategory.PRIVACY, RiskLevel.HIGH, "Capture approved camera input", True, False),
            C("privacy.microphone", "Use microphone", CapabilityCategory.PRIVACY, RiskLevel.HIGH, "Capture approved microphone input", True, False),
            C("privacy.screen_capture", "Capture screen", CapabilityCategory.PRIVACY, RiskLevel.HIGH, "Capture approved on-screen content", True, False),
            C("privacy.contacts", "Access contacts", CapabilityCategory.PRIVACY, RiskLevel.HIGH, "Read approved contact data", True, False),
            C("privacy.calendar", "Access calendar", CapabilityCategory.PRIVACY, RiskLevel.HIGH, "Read or modify approved calendar data", True, False),
            C("privacy.email", "Access email", CapabilityCategory.PRIVACY, RiskLevel.HIGH, "Read or send approved email", True, False),
            C("system.settings.modify", "Modify system settings", CapabilityCategory.SYSTEM, RiskLevel.CRITICAL, "Change operating-system settings", True, False),
            C("system.software.install", "Install system software", CapabilityCategory.SYSTEM, RiskLevel.CRITICAL, "Install operating-system software", True, False),
            C("system.registry.modify", "Modify registry", CapabilityCategory.SYSTEM, RiskLevel.CRITICAL, "Modify protected system registry data", True, False),
            C("system.restart", "Restart system", CapabilityCategory.SYSTEM, RiskLevel.CRITICAL, "Restart the current device", True, False, False),
            C("system.shutdown", "Shutdown system", CapabilityCategory.SYSTEM, RiskLevel.CRITICAL, "Shutdown the current device", True, False, False),
            C("system.remote_execute", "Remote execution", CapabilityCategory.SYSTEM, RiskLevel.CRITICAL, "Execute commands on an approved remote system", True, False),
            C("economy.spend", "Spend ACoin", CapabilityCategory.ECONOMY, RiskLevel.HIGH, "Spend currency or purchase assets", True, False),
            C("economy.trade", "Trade assets", CapabilityCategory.ECONOMY, RiskLevel.HIGH, "Transfer or trade user assets", True, False),
            C("governance.policy.manage", "Manage organization policy", CapabilityCategory.GOVERNANCE, RiskLevel.CRITICAL, "Manage shared roles and policy", True, False),
        )
