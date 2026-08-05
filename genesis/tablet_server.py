"""Serve the NeoGen web client and API from one local tablet process.

Run in Termux:
    python -m genesis.tablet_server

Then open:
    http://127.0.0.1:8080/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from genesis.api.server import ApiError, NeoGenApiHandler
from genesis.app.composition import create_workspace_runtime
from genesis.app.kernel import GenesisSettings
from genesis.app.workspace import WorkspaceService
from genesis.app.coding import CodeChange
from genesis.services.kernel import NeoGenKernel


class TabletHandler(NeoGenApiHandler):
    web_root: Path
    guarded_workspace: WorkspaceService

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/v1/guarded/workspace":
            try:
                user = self._authenticated_user()
                self._send(HTTPStatus.OK, self.guarded_workspace.snapshot(user.id))
            except ApiError as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/v1/guarded/repository":
            try:
                self._authenticated_user()
                self._send(HTTPStatus.OK, self.guarded_workspace.repository_snapshot())
            except ApiError as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/v1/guarded/repository/status":
            try:
                self._authenticated_user()
                self._send(
                    HTTPStatus.OK,
                    {
                        "status": self.guarded_workspace.repository_status(),
                        "log": self.guarded_workspace.repository_log(),
                        "diff": self.guarded_workspace.repository_diff(),
                    },
                )
            except ApiError as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/v1/guarded/code":
            try:
                self._authenticated_user()
                self._send(HTTPStatus.OK, {"items": self.guarded_workspace.code_inventory()})
            except ApiError as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/v1/guarded/code/read":
            try:
                self._authenticated_user()
                query = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
                target = unquote(query.get("path", ""))
                if not target:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "path is required")
                self._send(HTTPStatus.OK, self.guarded_workspace.read_code(target))
            except ApiError as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if path.startswith("/api/"):
            super().do_GET()
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/api/v1/guarded/"):
            super().do_POST()
            return
        try:
            user = self._authenticated_user()
            payload = self._read_json()
            project_id = user.id
            if path == "/api/v1/guarded/files/request-write":
                request = self.guarded_workspace.request_file_write(
                    project_id,
                    self._required(payload, "path"),
                    str(payload.get("content", "")),
                )
                self._send(HTTPStatus.ACCEPTED, request)
                return
            if path == "/api/v1/guarded/files/write":
                result = self.guarded_workspace.write_file(
                    project_id,
                    self._required(payload, "path"),
                    str(payload.get("content", "")),
                    self._required(payload, "approval_id"),
                )
                self._send(HTTPStatus.OK, {"path": result})
                return
            if path == "/api/v1/guarded/forge/layers/request":
                action = self._forge_layer_action(payload)
                avatar = self.kernel.game.forge_avatar(user.id, self._required(payload, "avatar_id"))
                cost = self.kernel.game.layer_cost(int(avatar["rarity_level"]), self._required(payload, "layer_type"))
                request = self.guarded_workspace.permissions.request(
                    project_id, "forge.layer", f"Spend {cost} COTD to forge the {payload['layer_type']} layer", action=action
                )
                self._send(HTTPStatus.ACCEPTED, request)
                return
            if path == "/api/v1/guarded/forge/layers/apply":
                action = self._forge_layer_action(payload)
                self.guarded_workspace.permissions.consume(
                    self._required(payload, "approval_id"), project_id, "forge.layer", action=action
                )
                result = self.kernel.game.add_forge_layer(
                    user.id, self._required(payload, "avatar_id"),
                    layer_type=self._required(payload, "layer_type"),
                    design_prompt=self._required(payload, "design_prompt"),
                    abilities=tuple(payload.get("abilities", ())),
                )
                self._send(HTTPStatus.CREATED, result)
                return
            if path == "/api/v1/guarded/forge/upgrade/request":
                avatar_id = self._required(payload, "avatar_id")
                avatar = self.kernel.game.forge_avatar(user.id, avatar_id)
                cost = self.kernel.game.rarity_upgrade_cost(int(avatar["rarity_level"]))
                action = json.dumps({"avatar_id": avatar_id, "from": avatar["rarity_level"], "cost": cost}, sort_keys=True)
                request = self.guarded_workspace.permissions.request(
                    project_id, "forge.upgrade", f"Spend {cost} COTD to upgrade rarity {avatar['rarity_level']} → {int(avatar['rarity_level']) + 1}", action=action
                )
                self._send(HTTPStatus.ACCEPTED, request)
                return
            if path == "/api/v1/guarded/forge/upgrade/apply":
                avatar_id = self._required(payload, "avatar_id")
                avatar = self.kernel.game.forge_avatar(user.id, avatar_id)
                cost = self.kernel.game.rarity_upgrade_cost(int(avatar["rarity_level"]))
                action = json.dumps({"avatar_id": avatar_id, "from": avatar["rarity_level"], "cost": cost}, sort_keys=True)
                self.guarded_workspace.permissions.consume(
                    self._required(payload, "approval_id"), project_id, "forge.upgrade", action=action
                )
                self._send(HTTPStatus.OK, self.kernel.game.upgrade_forge_avatar(user.id, avatar_id))
                return
            if path == "/api/v1/guarded/improvements/prepare":
                raw_changes = payload.get("changes")
                raw_commands = payload.get("verification_commands")
                if not isinstance(raw_changes, list) or not raw_changes:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "changes must be a non-empty list")
                if not isinstance(raw_commands, list) or not raw_commands:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "verification_commands must be a non-empty list")
                changes = tuple(
                    CodeChange(
                        self._required(item, "path"),
                        str(item.get("content", "")),
                        self._required(item, "expected_sha256"),
                    )
                    for item in raw_changes
                    if isinstance(item, dict)
                )
                commands = tuple(
                    tuple(command)
                    for command in raw_commands
                    if isinstance(command, list) and command and all(isinstance(arg, str) for arg in command)
                )
                if len(changes) != len(raw_changes) or len(commands) != len(raw_commands):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid change or verification command")
                plan = self.guarded_workspace.prepare_improvement(
                    project_id,
                    self._required(payload, "goal"),
                    changes,
                    commands,
                    strategy=str(payload.get("strategy", "vera-verified-edit")),
                )
                self._send(HTTPStatus.ACCEPTED, plan)
                return
            if path == "/api/v1/guarded/improvements/execute":
                plan = self.guarded_workspace.improvement_plan(self._required(payload, "plan_id"))
                if plan.project_id != project_id:
                    raise ApiError(HTTPStatus.FORBIDDEN, "Improvement belongs to another user")
                result = asyncio.run(self.guarded_workspace.execute_improvement(plan))
                self._send(HTTPStatus.OK, result)
                return
            if path == "/api/v1/guarded/terminal/request":
                command = payload.get("command")
                if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "command must be an argument list")
                request = self.guarded_workspace.request_terminal(project_id, tuple(command))
                self._send(HTTPStatus.ACCEPTED, request)
                return
            if path == "/api/v1/guarded/terminal/execute":
                command = payload.get("command")
                if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "command must be an argument list")
                result = asyncio.run(
                    self.guarded_workspace.run_terminal(
                        project_id,
                        tuple(command),
                        self._required(payload, "approval_id"),
                    )
                )
                self._send(HTTPStatus.OK, result)
                return
            if path == "/api/v1/guarded/repository/request":
                arguments = payload.get("arguments")
                if not isinstance(arguments, list) or not all(
                    isinstance(item, str) for item in arguments
                ):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "arguments must be a string list")
                request = self.guarded_workspace.request_repository(
                    project_id, tuple(arguments)
                )
                self._send(HTTPStatus.ACCEPTED, request)
                return
            if path == "/api/v1/guarded/repository/execute":
                arguments = payload.get("arguments")
                if not isinstance(arguments, list) or not all(
                    isinstance(item, str) for item in arguments
                ):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "arguments must be a string list")
                result = asyncio.run(
                    self.guarded_workspace.run_repository(
                        project_id,
                        tuple(arguments),
                        self._required(payload, "approval_id"),
                    )
                )
                self._send(HTTPStatus.OK, result)
                return
            if path == "/api/v1/guarded/approvals/decide":
                approved = payload.get("approved")
                if not isinstance(approved, bool):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "approved must be a boolean")
                current = self.guarded_workspace.permissions.require(
                    self._required(payload, "approval_id")
                )
                if current.project_id != project_id:
                    raise ApiError(HTTPStatus.FORBIDDEN, "Approval belongs to another user")
                decided = self.guarded_workspace.permissions.decide(current.id, approved=approved)
                self._send(HTTPStatus.OK, decided)
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except (KeyError, PermissionError, ValueError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(exc).__name__}: {exc}"})

    @staticmethod
    def _conversation_path(path: str, suffix: str) -> str | None:
        prefix = "/api/v1/conversations/"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        encoded = path[len(prefix):-len(suffix)].strip("/")
        return unquote(encoded) or None

    @staticmethod
    def _forge_layer_action(payload: dict[str, object]) -> str:
        abilities = payload.get("abilities", [])
        if not isinstance(abilities, list) or not all(isinstance(item, str) for item in abilities):
            raise ApiError(HTTPStatus.BAD_REQUEST, "abilities must be a string list")
        return json.dumps(
            {
                "avatar_id": str(payload.get("avatar_id", "")),
                "layer_type": str(payload.get("layer_type", "")),
                "design_prompt": str(payload.get("design_prompt", "")),
                "abilities": abilities,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        target = (self.web_root / relative).resolve()
        try:
            target.relative_to(self.web_root)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            target = self.web_root / "index.html"
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if target.name == "index.html":
            text = body.decode("utf-8")
            text = text.replace(
                'value="http://127.0.0.1:8080/api/v1"',
                'value="/api/v1"',
            )
            text = text.replace(
                "function apiBase(){return $('apiBase').value.replace(/\\/$/,'')}",
                "function apiBase(){const v=$('apiBase').value.trim();return (v&&v!=='/api/v1'?v:location.origin+'/api/v1').replace(/\\/$/,'')}",
            )
            text = text.replace(
                "const $=id=>document.getElementById(id);",
                "if('serviceWorker' in navigator){navigator.serviceWorker.getRegistrations().then(rs=>rs.forEach(r=>r.unregister()));}const $=id=>document.getElementById(id);",
            )
            body = text.encode("utf-8")

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)


def create_tablet_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    storage_path: str | Path = "neogen.db",
    workspace_path: str | Path = "workspace",
    web_path: str | Path | None = None,
) -> ThreadingHTTPServer:
    kernel = NeoGenKernel.build(
        storage_path=storage_path,
        workspace_path=workspace_path,
        enable_puter=True,
    )
    storage = Path(storage_path).resolve()
    guarded_runtime = create_workspace_runtime(
        GenesisSettings(
            data_dir=storage.parent / ".genesis",
            workspace_dir=Path(workspace_path).resolve(),
        )
    )
    asyncio.run(guarded_runtime.start())
    guarded_workspace = guarded_runtime.container.resolve("workspace", WorkspaceService)
    root = Path(web_path) if web_path else Path(__file__).resolve().parent.parent / "web"
    root = root.resolve()
    handler = type(
        "ConfiguredTabletHandler",
        (TabletHandler,),
        {
            "kernel": kernel,
            "web_root": root,
            "guarded_runtime": guarded_runtime,
            "guarded_workspace": guarded_workspace,
        },
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NeoGen locally on an Android tablet")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="neogen.db")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--web", default=None)
    args = parser.parse_args()

    server = create_tablet_server(
        host=args.host,
        port=args.port,
        storage_path=args.db,
        workspace_path=args.workspace,
        web_path=args.web,
    )
    try:
        print(f"NeoGen tablet server: http://{args.host}:{args.port}/")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.kernel.close()
        asyncio.run(server.RequestHandlerClass.guarded_runtime.stop())


if __name__ == "__main__":
    main()
