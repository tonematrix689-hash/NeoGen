"""Integration coverage for the NeoGen intelligent service kernel."""

from __future__ import annotations

import unittest

from genesis.services.agents import TaskStatus
from genesis.services.events import EventSeverity
from genesis.services.kernel import NeoGenKernel
from genesis.services.memory import MemoryDomain
from genesis.services.models import (
    ModelCapability,
    ModelDescriptor,
    ModelRequest,
    PrivacyLevel,
)
from genesis.services.permissions import PermissionScope
from genesis.services.planning import PlanStatus, StepKind
from genesis.services.plugins import PluginHealth, PluginManifest, PluginStatus
from genesis.services.projects import NodeKind, RelationKind
from genesis.services.tools import ToolRequest
from genesis.services.verification import VerificationStatus
from genesis.services.workflows import WorkflowStatus


class NeoGenCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = NeoGenKernel.build()

    def test_kernel_health_and_boot_event(self) -> None:
        health = self.kernel.health()
        self.assertEqual(health["status"], "healthy")
        self.assertGreaterEqual(health["tools"]["registered"], 6)
        events = self.kernel.events.replay(event_types=["KernelBuilt"])
        self.assertEqual(len(events), 1)

    def test_memory_versioning_and_search(self) -> None:
        record = self.kernel.memory.create(
            domain=MemoryDomain.PROJECT,
            owner_id="user:founder",
            title="NeoGen architecture",
            content="NeoGen coordinates models, tools, memory, and agents.",
            tags=["architecture", "kernel"],
            importance=0.9,
        )
        updated = self.kernel.memory.update(record.id, content="NeoGen is a governed AI operating system.")
        self.assertEqual(updated.version, 2)
        self.assertEqual(len(self.kernel.memory.history(record.id)), 2)
        found = self.kernel.memory.search(tags=["kernel"], text="governed")
        self.assertEqual(found[0].id, record.id)

    def test_permissions_gate_agent_execution(self) -> None:
        agent = self.kernel.agents.register(
            name="Terminal Agent",
            required_permissions=[PermissionScope.RUN_TERMINAL],
            handler=lambda task: task.payload["command"],
        )
        blocked_task = self.kernel.agents.enqueue(
            agent_id=agent.id,
            name="Run command",
            payload={"command": "python --version"},
            resource="workspace:neogen",
        )
        blocked = self.kernel.agents.run_next(agent.id)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.status, TaskStatus.BLOCKED)
        self.assertEqual(blocked.id, blocked_task.id)

        self.kernel.permissions.grant(
            subject_id=agent.id,
            scope=PermissionScope.RUN_TERMINAL,
            resource="workspace:neogen",
            granted_by="user:founder",
        )
        allowed_task = self.kernel.agents.enqueue(
            agent_id=agent.id,
            name="Run command",
            payload={"command": "python --version"},
            resource="workspace:neogen",
        )
        completed = self.kernel.agents.run_next(agent.id)
        self.assertEqual(completed.id, allowed_task.id)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)

    def test_workflow_coordinates_agents(self) -> None:
        agent = self.kernel.agents.register(
            name="Documentation Agent",
            handler=lambda task: {"documented": task.payload["topic"]},
        )
        step = self.kernel.workflows.make_step(
            name="Document kernel",
            agent_id=agent.id,
            task_name="Write documentation",
            payload={"topic": "NeoGen kernel"},
        )
        definition = self.kernel.workflows.define(name="Documentation workflow", steps=[step])
        run = self.kernel.workflows.start(definition.id, subject_id="user:founder")
        completed = self.kernel.workflows.run_to_completion(run.id)
        self.assertEqual(completed.status, WorkflowStatus.COMPLETED)
        self.assertEqual(completed.step_executions[0].result["documented"], "NeoGen kernel")

    def test_model_router_fails_over_and_records_metrics(self) -> None:
        self.kernel.models.register(
            ModelDescriptor(
                id="model:primary",
                provider="test",
                name="Primary",
                capabilities=frozenset({ModelCapability.REASONING}),
                context_window=32_000,
                supports_tools=True,
                supports_streaming=False,
                privacy_level=PrivacyLevel.PRIVATE,
                cost_score=0.4,
                latency_score=0.2,
                quality_score=0.95,
                reliability_score=0.9,
                priority=10,
            ),
            lambda request: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        )
        self.kernel.models.register(
            ModelDescriptor(
                id="model:fallback",
                provider="local",
                name="Fallback",
                capabilities=frozenset({ModelCapability.REASONING}),
                context_window=16_000,
                supports_tools=True,
                supports_streaming=False,
                privacy_level=PrivacyLevel.LOCAL_ONLY,
                cost_score=0.1,
                latency_score=0.3,
                quality_score=0.8,
                reliability_score=0.99,
            ),
            lambda request: "verified response",
        )
        response = self.kernel.models.complete(
            ModelRequest(
                capability=ModelCapability.REASONING,
                prompt="Explain NeoGen",
                require_tools=True,
                privacy_level=PrivacyLevel.PRIVATE,
            )
        )
        self.assertEqual(response.model_id, "model:fallback")
        self.assertEqual(self.kernel.models.metrics("model:primary").failures, 1)
        self.assertEqual(self.kernel.models.metrics("model:fallback").successes, 1)

    def test_plugin_lifecycle_is_permission_controlled(self) -> None:
        manifest = PluginManifest(
            id="plugin:github",
            name="GitHub",
            version="0.1.0",
            author="NeoGen",
            description="Repository integration",
            capabilities=frozenset({"repository.read"}),
            required_permissions=frozenset({PermissionScope.USE_NETWORK}),
            entrypoint="neogen.plugins.github:plugin",
        )
        self.kernel.plugins.discover(manifest)
        self.kernel.permissions.grant(
            subject_id="user:founder",
            scope=PermissionScope.USE_NETWORK,
            resource="plugin:plugin:github",
            granted_by="user:founder",
        )
        installed = self.kernel.plugins.install("plugin:github", subject_id="user:founder")
        self.assertEqual(installed.status, PluginStatus.INSTALLED)
        enabled = self.kernel.plugins.enable("plugin:github", subject_id="user:founder")
        self.assertEqual(enabled.status, PluginStatus.ENABLED)
        self.assertEqual(enabled.health, PluginHealth.HEALTHY)

    def test_project_intelligence_graph(self) -> None:
        project = self.kernel.projects.create_project("NeoGen")
        service = self.kernel.projects.add_node(
            project_id=project.id,
            kind=NodeKind.FILE,
            name="models.py",
            path="genesis/services/models.py",
        )
        test = self.kernel.projects.add_node(
            project_id=project.id,
            kind=NodeKind.TEST,
            name="test_neogen_core.py",
            path="tests/test_neogen_core.py",
        )
        self.kernel.projects.relate(source_id=test.id, target_id=service.id, kind=RelationKind.TESTS)
        self.assertEqual(self.kernel.projects.tests_for(service.id)[0].id, test.id)
        self.kernel.projects.set_build_status(project.id, "passing")
        snapshot = self.kernel.projects.snapshot(project.id)
        self.assertEqual(snapshot.build_status, "passing")
        self.assertEqual(snapshot.files, 1)
        self.assertEqual(snapshot.tests, 1)

    def test_event_delivery_failure_is_isolated(self) -> None:
        delivered: list[str] = []
        self.kernel.events.subscribe("SystemCheck", lambda event: delivered.append(event.id))
        self.kernel.events.subscribe(
            "SystemCheck",
            lambda event: (_ for _ in ()).throw(RuntimeError("subscriber failure")),
            subscriber_id="broken",
        )
        event = self.kernel.events.publish(
            "SystemCheck",
            source="tests",
            severity=EventSeverity.WARNING,
        )
        self.assertEqual(delivered, [event.id])
        self.assertEqual(len(self.kernel.events.failures()), 1)

    def test_puter_provider_is_registered_and_permission_gated(self) -> None:
        puter_tools = self.kernel.tools.find(capability="provider.puter")
        self.assertEqual(len(puter_tools), 6)
        subject = "user:founder"
        resource = "workspace:neogen"
        for scope in (PermissionScope.USE_MODELS, PermissionScope.USE_NETWORK):
            self.kernel.permissions.grant(
                subject_id=subject,
                scope=scope,
                resource=resource,
                granted_by=subject,
            )
        result = self.kernel.tools.execute(
            ToolRequest(
                subject_id=subject,
                tool_id="puter.ai",
                operation="ai.chat",
                arguments={"prompt": "Explain NeoGen"},
                resource=resource,
                correlation_id="test-puter-ai",
            )
        )
        self.assertTrue(result.success)
        self.assertEqual(result.output["provider"], "puter")
        self.assertEqual(result.output["execution_target"], "browser")

    def test_planning_engine_detects_approval_requirements(self) -> None:
        step = self.kernel.planning.make_step(
            name="Publish dashboard",
            kind=StepKind.TOOL,
            description="Publish the dashboard through Puter hosting.",
            required_permissions=[PermissionScope.DEPLOY, PermissionScope.USE_NETWORK],
            resource="workspace:neogen",
            tool_id="puter.hosting",
            estimated_cost=0.1,
            estimated_seconds=30,
            risk=0.9,
            verification="Confirm hosting endpoint is reachable.",
        )
        plan = self.kernel.planning.create_plan(
            subject_id="user:founder",
            goal="Publish NeoGen dashboard",
            steps=[step],
            success_criteria=["Dashboard is reachable"],
        )
        self.assertEqual(plan.status, PlanStatus.APPROVAL_REQUIRED)
        self.assertIn(PermissionScope.DEPLOY, plan.missing_permissions)
        requests = self.kernel.planning.approval_requests(plan.id)
        self.assertEqual(len(requests), 2)

    def test_verification_engine_reports_weighted_confidence(self) -> None:
        nonempty = self.kernel.verification.register(
            name="Non-empty output",
            description="Ensure the result contains output.",
            handler=lambda value: (bool(value), "output present", {"length": len(value)}, 0.95),
            required=True,
            weight=2,
        )
        contains_keyword = self.kernel.verification.register(
            name="Contains NeoGen",
            description="Ensure the result references NeoGen.",
            handler=lambda value: ("NeoGen" in value, "keyword checked", {}, 0.85),
            required=True,
            weight=1,
        )
        report = self.kernel.verification.verify(
            subject="assistant response",
            value="NeoGen verified output",
            check_ids=[nonempty.id, contains_keyword.id],
        )
        self.assertTrue(report.passed)
        self.assertGreater(report.confidence, 0.8)
        self.assertTrue(all(result.status is VerificationStatus.PASSED for result in report.results))


if __name__ == "__main__":
    unittest.main()
