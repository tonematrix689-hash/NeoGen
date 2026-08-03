"""Dependency-free REST API for the NeoGen kernel."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from genesis.services.conversations import ConversationError
from genesis.services.identity import IdentityError
from genesis.services.kernel import NeoGenKernel
from genesis.services.permissions import PermissionScope
from genesis.services.terminal import TerminalError
from genesis.services.tools import ToolRequest
from genesis.services.workspace import WorkspaceError


class ApiError(RuntimeError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


class NeoGenApiHandler(BaseHTTPRequestHandler):
    kernel: NeoGenKernel
    server_version = "NeoGenAPI/0.4"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path in {"/", "/api/v1"}:
                self._send(HTTPStatus.OK, {"name": "NeoGen API", "version": "v1", "server": self.server_version})
                return
            if path == "/api/v1/health":
                self._send(HTTPStatus.OK, self.kernel.health())
                return
            if path == "/api/v1/auth/me":
                self._send(HTTPStatus.OK, self._authenticated_user())
                return

            user = self._authenticated_user()
            if path == "/api/v1/conversations":
                self._send(HTTPStatus.OK, {"items": self.kernel.conversations.list(user_id=user.id)})
                return
            conversation_id = self._conversation_path(path, suffix="/messages")
            if conversation_id:
                self._send(HTTPStatus.OK, {
                    "conversation": self.kernel.conversations.get(conversation_id, user_id=user.id),
                    "items": self.kernel.conversations.messages(conversation_id, user_id=user.id),
                })
                return
            if path == "/api/v1/workspace/list":
                target = query.get("path", [""])[0]
                recursive = query.get("recursive", ["false"])[0].lower() in {"1", "true", "yes"}
                self._send(HTTPStatus.OK, {"items": self.kernel.workspace.list(target, recursive=recursive)})
                return
            if path == "/api/v1/workspace/read":
                target = query.get("path", [""])[0]
                if not target:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "path is required")
                self._send(HTTPStatus.OK, self.kernel.workspace.read(target))
                return
            if path == "/api/v1/terminal/commands":
                self._send(HTTPStatus.OK, {"items": self.kernel.terminal.available_commands()})
                return
            if path == "/api/v1/tools":
                self._send(HTTPStatus.OK, {"items": self.kernel.tools.find()})
                return
            if path == "/api/v1/checkpoints":
                records = self.kernel.storage.list(self.kernel.checkpoints.namespace)
                self._send(HTTPStatus.OK, {"items": [record.value for record in records]})
                return
            if path == "/api/v1/events":
                self._send(HTTPStatus.OK, {"items": self.kernel.events.replay()})
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except IdentityError as exc:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        except (ConversationError, WorkspaceError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            payload = self._read_json()
            if path == "/api/v1/auth/register":
                user = self.kernel.identity.register(
                    email=self._required(payload, "email"),
                    password=self._required(payload, "password"),
                    display_name=self._required(payload, "display_name"),
                )
                self._ensure_chat_permissions(user.id)
                self._send(HTTPStatus.CREATED, user)
                return
            if path == "/api/v1/auth/login":
                session = self.kernel.identity.authenticate(
                    email=self._required(payload, "email"),
                    password=self._required(payload, "password"),
                    session_hours=int(payload.get("session_hours", 24)),
                )
                self._ensure_chat_permissions(session.user_id)
                self._send(HTTPStatus.OK, session)
                return
            if path == "/api/v1/auth/logout":
                self.kernel.identity.logout(self._bearer_token())
                self._send(HTTPStatus.OK, {"logged_out": True})
                return

            user = self._authenticated_user()
            if path == "/api/v1/conversations":
                self._send(HTTPStatus.CREATED, self.kernel.conversations.create(
                    user_id=user.id,
                    title=str(payload.get("title", "New conversation")),
                ))
                return
            conversation_id = self._conversation_path(path, suffix="/chat")
            if conversation_id:
                self._ensure_chat_permissions(user.id)
                self._send(HTTPStatus.ACCEPTED, self.kernel.conversations.request_ai_response(
                    conversation_id=conversation_id,
                    user_id=user.id,
                    prompt=self._required(payload, "prompt"),
                    resource=str(payload.get("resource", "workspace:neogen")),
                    model=str(payload["model"]) if payload.get("model") else None,
                ))
                return
            conversation_id = self._conversation_path(path, suffix="/responses")
            if conversation_id:
                self._send(HTTPStatus.CREATED, self.kernel.conversations.record_ai_response(
                    conversation_id=conversation_id,
                    user_id=user.id,
                    content=self._required(payload, "content"),
                    provider=str(payload.get("provider", "puter")),
                    model=str(payload["model"]) if payload.get("model") else None,
                ))
                return
            if path == "/api/v1/workspace/write":
                self._send(HTTPStatus.OK, self.kernel.workspace.write(
                    self._required(payload, "path"),
                    str(payload.get("content", "")),
                    create_parents=bool(payload.get("create_parents", True)),
                    expected_sha256=str(payload["expected_sha256"]) if payload.get("expected_sha256") else None,
                ))
                return
            if path == "/api/v1/workspace/mkdir":
                self._send(HTTPStatus.CREATED, self.kernel.workspace.create_directory(self._required(payload, "path")))
                return
            if path == "/api/v1/workspace/delete":
                self._send(HTTPStatus.OK, self.kernel.workspace.delete(
                    self._required(payload, "path"),
                    recursive=bool(payload.get("recursive", False)),
                ))
                return
            if path == "/api/v1/terminal/execute":
                command = payload.get("command")
                if not isinstance(command, list):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "command must be an argument list")
                self._send(HTTPStatus.OK, self.kernel.terminal.execute(
                    command,
                    cwd=str(payload.get("cwd", "")),
                    timeout_seconds=int(payload["timeout_seconds"]) if payload.get("timeout_seconds") else None,
                    env=dict(payload.get("env", {})),
                    stdin=str(payload["stdin"]) if payload.get("stdin") is not None else None,
                ))
                return
            if path == "/api/v1/checkpoints":
                self._send(HTTPStatus.CREATED, self.kernel.checkpoints.save(
                    category=self._required(payload, "category"),
                    subject_id=str(payload.get("subject_id") or user.id),
                    state=payload.get("state", {}),
                    checkpoint_id=payload.get("checkpoint_id"),
                ))
                return
            if path == "/api/v1/permissions/grant":
                if "admin" not in user.roles:
                    raise ApiError(HTTPStatus.FORBIDDEN, "Admin role required")
                scope_name = self._required(payload, "scope")
                try:
                    scope = PermissionScope(scope_name)
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, f"Unknown permission scope: {scope_name}") from exc
                self._send(HTTPStatus.CREATED, self.kernel.permissions.grant(
                    subject_id=self._required(payload, "subject_id"),
                    scope=scope,
                    resource=self._required(payload, "resource"),
                    granted_by=user.id,
                ))
                return
            if path == "/api/v1/tools/execute":
                self._send(HTTPStatus.OK, self.kernel.tools.execute(ToolRequest(
                    subject_id=user.id,
                    tool_id=self._required(payload, "tool_id"),
                    operation=self._required(payload, "operation"),
                    arguments=dict(payload.get("arguments", {})),
                    resource=str(payload.get("resource", "*")),
                    correlation_id=payload.get("correlation_id"),
                )))
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except IdentityError as exc:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        except (ConversationError, WorkspaceError, TerminalError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:
        self.kernel.events.publish("ApiRequest", source="neogen.api", payload={
            "client": self.client_address[0],
            "message": format % args,
        })

    def _authenticated_user(self):
        return self.kernel.identity.resolve(self._bearer_token())

    def _bearer_token(self) -> str:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or not header[7:].strip():
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Bearer token required")
        return header[7:].strip()

    def _ensure_chat_permissions(self, user_id: str) -> None:
        for scope in (PermissionScope.USE_MODELS, PermissionScope.USE_NETWORK):
            if not self.kernel.permissions.check(
                subject_id=user_id,
                scope=scope,
                resource="workspace:neogen",
            ).allowed:
                self.kernel.permissions.grant(
                    subject_id=user_id,
                    scope=scope,
                    resource="workspace:neogen",
                    granted_by="system:chat-bootstrap",
                )

    @staticmethod
    def _conversation_path(path: str, *, suffix: str) -> str | None:
        prefix = "/api/v1/conversations/"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        return path[len(prefix):-len(suffix)].strip("/") or None

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length") from exc
        if length <= 0:
            return {}
        if length > 2_500_000:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body exceeds 2.5 MB")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object")
        return value

    def _send(self, status: HTTPStatus, value: Any) -> None:
        body = json.dumps(_jsonable(value), separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    @staticmethod
    def _required(payload: dict[str, Any], field: str) -> str:
        value = str(payload.get(field, "")).strip()
        if not value:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{field} is required")
        return value


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    storage_path: str | Path = "neogen.db",
    workspace_path: str | Path = "workspace",
    enable_puter: bool = True,
) -> ThreadingHTTPServer:
    kernel = NeoGenKernel.build(
        storage_path=storage_path,
        workspace_path=workspace_path,
        enable_puter=enable_puter,
    )
    handler = type("ConfiguredNeoGenApiHandler", (NeoGenApiHandler,), {"kernel": kernel})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the NeoGen REST API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="neogen.db")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--disable-puter", action="store_true")
    args = parser.parse_args()
    server = create_server(
        host=args.host,
        port=args.port,
        storage_path=args.db,
        workspace_path=args.workspace,
        enable_puter=not args.disable_puter,
    )
    try:
        print(f"NeoGen API listening on http://{args.host}:{args.port}")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.kernel.close()


if __name__ == "__main__":
    main()
