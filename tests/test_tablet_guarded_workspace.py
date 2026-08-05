"""HTTP integration tests for the approval-gated tablet workspace."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from genesis.tablet_server import create_tablet_server


class GuardedTabletWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.server = create_tablet_server(
            host="127.0.0.1",
            port=0,
            storage_path=root / "neogen.db",
            workspace_path=root / "workspace",
        )
        self.workspace = root / "workspace"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}/api/v1"
        self.post(
            "/auth/register",
            {
                "email": "guarded@example.com",
                "password": "guarded-password-123",
                "display_name": "Guarded User",
            },
        )
        session = self.post(
            "/auth/login",
            {"email": "guarded@example.com", "password": "guarded-password-123"},
        )
        self.token = session["token"]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server.RequestHandlerClass.kernel.close()
        asyncio.run(self.server.RequestHandlerClass.guarded_runtime.stop())
        self.temp.cleanup()

    def post(self, path: str, payload: dict[str, object], *, authenticated: bool = False):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        authenticated: bool = False,
    ):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def get_text(self, path: str) -> str:
        host, port = self.server.server_address
        with urlopen(f"http://{host}:{port}{path}", timeout=5) as response:
            return response.read().decode("utf-8")

    def test_file_write_requires_exact_single_use_approval(self) -> None:
        action = {"path": "notes/plan.txt", "content": "Continue NeoGen"}
        approval = self.post(
            "/guarded/files/request-write", action, authenticated=True
        )

        with self.assertRaises(HTTPError) as unapproved:
            self.post(
                "/guarded/files/write",
                {**action, "approval_id": approval["id"]},
                authenticated=True,
            )
        self.assertEqual(unapproved.exception.code, 400)

        self.post(
            "/guarded/approvals/decide",
            {"approval_id": approval["id"], "approved": True},
            authenticated=True,
        )
        self.post(
            "/guarded/files/write",
            {**action, "approval_id": approval["id"]},
            authenticated=True,
        )
        self.assertEqual(
            (self.workspace / "notes" / "plan.txt").read_text(encoding="utf-8"),
            "Continue NeoGen",
        )

        with self.assertRaises(HTTPError) as reused:
            self.post(
                "/guarded/files/write",
                {**action, "approval_id": approval["id"]},
                authenticated=True,
            )
        self.assertEqual(reused.exception.code, 400)

    def test_terminal_approval_is_bound_to_exact_arguments(self) -> None:
        command = [sys.executable, "-c", "print('approved')"]
        approval = self.post(
            "/guarded/terminal/request", {"command": command}, authenticated=True
        )
        self.post(
            "/guarded/approvals/decide",
            {"approval_id": approval["id"], "approved": True},
            authenticated=True,
        )

        with self.assertRaises(HTTPError) as substituted:
            self.post(
                "/guarded/terminal/execute",
                {
                    "command": [sys.executable, "-c", "print('substituted')"],
                    "approval_id": approval["id"],
                },
                authenticated=True,
            )
        self.assertEqual(substituted.exception.code, 400)

        result = self.post(
            "/guarded/terminal/execute",
            {"command": command, "approval_id": approval["id"]},
            authenticated=True,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("approved", result["stdout"])

    def test_verified_improvement_uses_one_approval_and_runs_checks(self) -> None:
        source = self.workspace / "value.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        inspected = self.request_json(
            "GET", "/guarded/code/read?path=value.py", authenticated=True
        )
        plan = self.post(
            "/guarded/improvements/prepare",
            {
                "goal": "Raise the verified value",
                "changes": [{
                    "path": "value.py",
                    "content": "VALUE = 2\n",
                    "expected_sha256": inspected["sha256"],
                }],
                "verification_commands": [[
                    sys.executable, "-c", "import value; assert value.VALUE == 2",
                ]],
            },
            authenticated=True,
        )
        self.post(
            "/guarded/approvals/decide",
            {"approval_id": plan["approval"]["id"], "approved": True},
            authenticated=True,
        )
        result = self.post(
            "/guarded/improvements/execute",
            {"plan_id": plan["id"]},
            authenticated=True,
        )
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 2\n")
        self.assertEqual(len(result["verification_results"]), 1)

    def test_cross_conversation_memory_search_is_user_scoped(self) -> None:
        first = self.post("/conversations", {"title": "Architecture"}, authenticated=True)
        encoded = first["id"].replace(":", "%3A")
        self.post(
            f"/conversations/{encoded}/chat",
            {"prompt": "Keep the recovery checkpoint before every verified edit"},
            authenticated=True,
        )
        found = self.request_json(
            "GET", "/conversations/search?q=recovery%20checkpoint", authenticated=True
        )
        self.assertEqual(len(found["items"]), 1)
        self.assertEqual(found["items"][0]["conversation_title"], "Architecture")

    def test_conversation_history_can_be_renamed_and_deleted(self) -> None:
        conversation = self.post(
            "/conversations", {"title": "New conversation"}, authenticated=True
        )
        encoded_id = conversation["id"].replace(":", "%3A")
        renamed = self.request_json(
            "PATCH",
            f"/conversations/{encoded_id}",
            {"title": "NeoGen redesign"},
            authenticated=True,
        )
        self.assertEqual(renamed["title"], "NeoGen redesign")

        deleted = self.request_json(
            "DELETE", f"/conversations/{encoded_id}", authenticated=True
        )
        self.assertTrue(deleted["deleted"])
        listing = self.request_json("GET", "/conversations", authenticated=True)
        self.assertNotIn(conversation["id"], [item["id"] for item in listing["items"]])

    def test_assistant_first_ui_exposes_scoped_approvals_and_canvas(self) -> None:
        page = self.get_text("/")
        self.assertIn('id="landingTop"', page)
        self.assertEqual(page.count('data-plan-card="level-'), 10)
        self.assertIn('data-plan-card="business"', page)
        self.assertIn('data-plan-card="enterprise"', page)
        self.assertIn('class="silica-core"', page)
        self.assertIn('id="chatView"', page)
        self.assertIn('id="approvalCard"', page)
        self.assertIn('id="approveAction"', page)
        self.assertIn('id="resultCanvas"', page)
        self.assertIn('id="councilView"', page)
        self.assertIn('id="agentGrid"', page)
        self.assertIn('id="runCouncil"', page)
        self.assertIn('id="includeCouncilRepository"', page)
        self.assertIn('id="refreshCouncilRepository"', page)
        self.assertIn('id="saveCouncilRepository"', page)
        self.assertIn('id="handoffCouncil"', page)
        self.assertIn('id="trainingView"', page)
        self.assertIn('id="startTraining"', page)
        self.assertIn('id="settingsPlanGrid"', page)
        self.assertIn('id="settingsAbilityGrid"', page)
        self.assertIn('data-ability="agent_council"', page)
        self.assertIn('data-ability="static_publish"', page)
        self.assertIn('src="https://js.puter.com/v2/"', page)

        client = self.get_text("/assets/neogen.js")
        self.assertIn("requestUserApproval", client)
        self.assertIn("completeAction", client)
        self.assertIn("COUNCIL_ROLES", client)
        self.assertIn("runAgentCouncil", client)
        self.assertIn("saveCouncilTranscript", client)
        self.assertIn("loadCouncilRepositoryContext", client)
        self.assertIn("saveCouncilTranscriptToRepository", client)
        self.assertIn("handoffCouncilImprovement", client)
        self.assertIn("Cross-analyse the repository evidence", client)
        council_roles = client.split("const COUNCIL_ROLES = [", 1)[1].split("];", 1)[0]
        self.assertEqual(council_roles.count('{ id: "'), 10)
        self.assertIn("startTrainingResearch", client)
        self.assertIn("PLAN_LABELS", client)
        self.assertIn('admin: "Level 11 · Admin"', client)
        self.assertIn('owner: "Level 12 · Owner"', client)
        ability_catalog = client.split("const ABILITY_CATALOG = [", 1)[1].split("];", 1)[0]
        self.assertEqual(ability_catalog.count('{ id: "'), 36)
        self.assertIn('id: "subscription_admin"', ability_catalog)
        self.assertIn('id: "emergency_recovery"', ability_catalog)
        self.assertIn("applyEntitlements", client)
        self.assertIn("loadSubscription", client)
        self.assertIn("settingsLocalIdentity", client)
        self.assertIn("Level 12 · Owner", client)
        self.assertIn("prepare_verified_improvement", client)
        self.assertIn("search_conversation_memory", client)
        self.assertIn("one bundled user approval", client)

        styles = self.get_text("/assets/neogen.css")
        self.assertIn("Silica Matrix landing", styles)
        self.assertIn(".orbit-blue", styles)
        self.assertIn("--accent-gold", styles)

    def test_subscription_catalog_requests_and_activation(self) -> None:
        catalog = self.request_json("GET", "/subscriptions/catalog")
        self.assertEqual(len(catalog["items"]), 14)
        self.assertEqual(
            [plan["level"] for plan in catalog["items"][:10]], list(range(1, 11))
        )

        current = self.request_json("GET", "/subscriptions/current", authenticated=True)
        self.assertEqual(current["plan"]["id"], "owner")
        self.assertEqual(current["plan"]["level"], 12)
        self.assertEqual(current["subscription"]["state"], "active")

        requested = self.request_json(
            "POST", "/subscriptions/request", {"plan_id": "level-9"}, authenticated=True
        )
        self.assertTrue(requested["checkout_required"])
        self.assertEqual(requested["subscription"]["state"], "pending_provider")
        current = self.request_json("GET", "/subscriptions/current", authenticated=True)
        self.assertEqual(current["plan"]["id"], "owner")

        user = self.request_json("GET", "/auth/me", authenticated=True)
        activated = self.request_json(
            "POST",
            "/subscriptions/activate",
            {"user_id": user["id"], "plan_id": "level-9", "provider": "test"},
            authenticated=True,
        )
        self.assertEqual(activated["plan_id"], "level-9")
        current = self.request_json("GET", "/subscriptions/current", authenticated=True)
        self.assertIn("agent_council", current["plan"]["abilities"])

    def test_forge_spending_requires_exact_single_use_approval(self) -> None:
        avatar = self.post(
            "/forge/avatars",
            {"name": "Sixfold", "prompt": "A six-armed antlered guardian"},
            authenticated=True,
        )
        action = {
            "avatar_id": avatar["id"],
            "layer_type": "bones",
            "design_prompt": "A branching luminous skeleton",
            "abilities": ["six-limb coordination"],
        }
        approval = self.post("/guarded/forge/layers/request", action, authenticated=True)

        with self.assertRaises(HTTPError) as unapproved:
            self.post(
                "/guarded/forge/layers/apply",
                {**action, "approval_id": approval["id"]},
                authenticated=True,
            )
        self.assertEqual(unapproved.exception.code, 400)
        self.post(
            "/guarded/approvals/decide",
            {"approval_id": approval["id"], "approved": True},
            authenticated=True,
        )
        with self.assertRaises(HTTPError) as substituted:
            self.post(
                "/guarded/forge/layers/apply",
                {**action, "design_prompt": "Substituted", "approval_id": approval["id"]},
                authenticated=True,
            )
        self.assertEqual(substituted.exception.code, 400)

        forged = self.post(
            "/guarded/forge/layers/apply",
            {**action, "approval_id": approval["id"]},
            authenticated=True,
        )
        self.assertEqual(forged["layers"]["bones"]["cost"], 30)
        wallet = self.request_json("GET", "/wallet", authenticated=True)
        self.assertEqual(wallet["balance"], 970)

        upgrade = self.post(
            "/guarded/forge/upgrade/request", {"avatar_id": avatar["id"]}, authenticated=True
        )
        self.post(
            "/guarded/approvals/decide",
            {"approval_id": upgrade["id"], "approved": True},
            authenticated=True,
        )
        evolved = self.post(
            "/guarded/forge/upgrade/apply",
            {"avatar_id": avatar["id"], "approval_id": upgrade["id"]},
            authenticated=True,
        )
        self.assertEqual(evolved["rarity_level"], 2)

        with self.assertRaises(HTTPError) as direct:
            self.post("/forge/upgrade", {"avatar_id": avatar["id"]}, authenticated=True)
        self.assertEqual(direct.exception.code, 404)

    def test_decision_symbiosis_is_owner_scoped_and_risk_adaptive(self) -> None:
        decision = self.post(
            "/guarded/symbiosis/decisions",
            {"statement": "Prefer reversible changes", "context": "NeoGen releases", "confidence": 0.9},
            authenticated=True,
        )
        listed = self.request_json("GET", "/guarded/symbiosis/decisions", authenticated=True)
        self.assertEqual(listed["items"][0]["id"], decision["id"])
        assessed = self.post(
            "/guarded/symbiosis/assess",
            {"risk": 0.3, "sensitive": True, "irreversible": True},
            authenticated=True,
        )
        self.assertEqual(assessed["mode"], "human_only")
        self.assertTrue(assessed["approval_required"])
        revoked = self.post(
            "/guarded/symbiosis/decisions/update",
            {"decision_id": decision["id"], "revoke": True},
            authenticated=True,
        )
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(
            self.request_json("GET", "/guarded/symbiosis/decisions", authenticated=True)["items"], []
        )


if __name__ == "__main__":
    unittest.main()
