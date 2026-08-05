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
from urllib.parse import parse_qs, unquote, urlparse

from genesis.services.conversations import ConversationError
from genesis.services.game import GameError
from genesis.services.identity import IdentityError
from genesis.services.legal import LegalError
from genesis.services.kernel import NeoGenKernel
from genesis.services.permissions import PermissionScope
from genesis.services.subscriptions import SubscriptionError
from genesis.services.terminal import TerminalError
from genesis.services.tools import ToolRequest
from genesis.services.workspace import WorkspaceError


class ApiError(RuntimeError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _jsonable(value: Any) -> Any:
    if is_dataclass(value): return _jsonable(asdict(value))
    if isinstance(value, Enum): return value.value
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, dict): return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)): return [_jsonable(v) for v in value]
    return value


class NeoGenApiHandler(BaseHTTPRequestHandler):
    kernel: NeoGenKernel
    server_version = "NeoGenAPI/0.6"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT); self._cors_headers(); self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path); path = parsed.path; query = parse_qs(parsed.query)
            if path in {"/", "/api/v1"}:
                self._send(HTTPStatus.OK, {"name":"NeoGen API","version":"v1","server":self.server_version}); return
            if path == "/api/v1/health": self._send(HTTPStatus.OK, self.kernel.health()); return
            if path == "/api/v1/subscriptions/catalog": self._send(HTTPStatus.OK, {"items": self.kernel.subscriptions.catalog()}); return
            if path == "/api/v1/legal/catalog": self._send(HTTPStatus.OK, {"items": self.kernel.legal.catalog(), "configuration": self.kernel.legal.public_configuration()}); return
            if path == "/api/v1/auth/me": self._send(HTTPStatus.OK, self._authenticated_user()); return
            user = self._authenticated_user()
            if path == "/api/v1/subscriptions/current": self._send(HTTPStatus.OK, self.kernel.subscriptions.current(user.id)); return
            if path == "/api/v1/legal/status": self._send(HTTPStatus.OK, self.kernel.legal.current_acceptance(user.id)); return
            if path == "/api/v1/avatar": self._send(HTTPStatus.OK, self.kernel.game.get_or_create_avatar(user.id)); return
            if path == "/api/v1/inventory": self._send(HTTPStatus.OK, {"items": self.kernel.game.inventory(user.id)}); return
            if path == "/api/v1/wallet": self._send(HTTPStatus.OK, self.kernel.game.wallet(user.id)); return
            if path == "/api/v1/wallet/transactions": self._send(HTTPStatus.OK, {"items": self.kernel.game.transactions(user.id)}); return
            if path == "/api/v1/marketplace": self._send(HTTPStatus.OK, {"items": self.kernel.game.listings()}); return
            if path == "/api/v1/conversations": self._send(HTTPStatus.OK, {"items": self.kernel.conversations.list(user_id=user.id)}); return
            conversation_id = self._conversation_path(path, "/messages")
            if conversation_id:
                self._send(HTTPStatus.OK, {"conversation": self.kernel.conversations.get(conversation_id,user_id=user.id),"items":self.kernel.conversations.messages(conversation_id,user_id=user.id)}); return
            if path == "/api/v1/workspace/list":
                self._send(HTTPStatus.OK,{"items":self.kernel.workspace.list(query.get("path",[""])[0],recursive=query.get("recursive",["false"])[0].lower() in {"1","true","yes"})}); return
            if path == "/api/v1/workspace/read":
                target=query.get("path",[""])[0]
                if not target: raise ApiError(HTTPStatus.BAD_REQUEST,"path is required")
                self._send(HTTPStatus.OK,self.kernel.workspace.read(target)); return
            if path == "/api/v1/terminal/commands": self._send(HTTPStatus.OK,{"items":self.kernel.terminal.available_commands()}); return
            if path == "/api/v1/tools": self._send(HTTPStatus.OK,{"items":self.kernel.tools.find()}); return
            if path == "/api/v1/checkpoints": self._send(HTTPStatus.OK,{"items":[r.value for r in self.kernel.storage.list(self.kernel.checkpoints.namespace)]}); return
            if path == "/api/v1/events": self._send(HTTPStatus.OK,{"items":self.kernel.events.replay()}); return
            raise ApiError(HTTPStatus.NOT_FOUND,"Endpoint not found")
        except ApiError as exc: self._send(exc.status,{"error":str(exc)})
        except IdentityError as exc: self._send(HTTPStatus.UNAUTHORIZED,{"error":str(exc)})
        except (ConversationError,WorkspaceError,GameError) as exc: self._send(HTTPStatus.BAD_REQUEST,{"error":str(exc)})
        except Exception as exc: self._send(HTTPStatus.INTERNAL_SERVER_ERROR,{"error":f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path=urlparse(self.path).path; payload=self._read_json()
            if path == "/api/v1/auth/register":
                user=self.kernel.identity.register(email=self._required(payload,"email"),password=self._required(payload,"password"),display_name=self._required(payload,"display_name")); self._ensure_chat_permissions(user.id); self.kernel.game.get_or_create_avatar(user.id); self._ensure_role_entitlement(user); self._send(HTTPStatus.CREATED,user); return
            if path == "/api/v1/auth/login":
                session=self.kernel.identity.authenticate(email=self._required(payload,"email"),password=self._required(payload,"password"),session_hours=int(payload.get("session_hours",24))); self._ensure_chat_permissions(session.user_id); self.kernel.game.get_or_create_avatar(session.user_id); self._ensure_role_entitlement(self.kernel.identity.get_user(session.user_id)); self._send(HTTPStatus.OK,session); return
            if path == "/api/v1/auth/logout": self.kernel.identity.logout(self._bearer_token()); self._send(HTTPStatus.OK,{"logged_out":True}); return
            user=self._authenticated_user()
            if path == "/api/v1/subscriptions/request": self._send(HTTPStatus.ACCEPTED,self.kernel.subscriptions.request(user.id,self._required(payload,"plan_id"))); return
            if path == "/api/v1/legal/acceptance":
                documents=payload.get("documents")
                if not isinstance(documents,dict): raise ApiError(HTTPStatus.BAD_REQUEST,"documents must be an object of document versions")
                self._send(HTTPStatus.CREATED,self.kernel.legal.accept(user.id,documents,age_confirmed=bool(payload.get("age_confirmed")),locale=str(payload.get("locale", "")),source=str(payload.get("source", "web")))); return
            if path == "/api/v1/subscriptions/activate":
                if "admin" not in user.roles: raise ApiError(HTTPStatus.FORBIDDEN,"Admin role required")
                target_id=str(payload.get("user_id") or user.id); plan_id=self._required(payload,"plan_id"); target=self.kernel.identity.get_user(target_id)
                if plan_id == "owner" and ("owner" not in user.roles or "owner" not in target.roles): raise ApiError(HTTPStatus.FORBIDDEN,"Owner role required")
                if plan_id == "admin" and "admin" not in target.roles: raise ApiError(HTTPStatus.FORBIDDEN,"Target user must have the admin role")
                self._send(HTTPStatus.OK,self.kernel.subscriptions.activate(target_id,plan_id,provider=str(payload.get("provider") or "manual-admin"))); return
            if path == "/api/v1/avatar": self._send(HTTPStatus.OK,self.kernel.game.update_avatar(user.id,name=str(payload["name"]) if payload.get("name") is not None else None,appearance=dict(payload["appearance"]) if payload.get("appearance") is not None else None)); return
            if path == "/api/v1/inventory/grant":
                if "admin" not in user.roles: raise ApiError(HTTPStatus.FORBIDDEN,"Admin role required")
                self._send(HTTPStatus.CREATED,self.kernel.game.grant_item(str(payload.get("user_id") or user.id),item_type=self._required(payload,"item_type"),name=self._required(payload,"name"),rarity=int(payload.get("rarity",1)),metadata=dict(payload.get("metadata",{})))); return
            if path == "/api/v1/wallet/credit":
                if "admin" not in user.roles: raise ApiError(HTTPStatus.FORBIDDEN,"Admin role required")
                self._send(HTTPStatus.OK,self.kernel.game.credit(str(payload.get("user_id") or user.id),int(payload.get("amount",0)),reason=str(payload.get("reason","reward")))); return
            if path == "/api/v1/marketplace/list": self._send(HTTPStatus.CREATED,self.kernel.game.create_listing(user.id,name=self._required(payload,"name"),description=str(payload.get("description","")),price=int(payload.get("price",0)),item=dict(payload.get("item",{})))); return
            if path == "/api/v1/marketplace/purchase": self._send(HTTPStatus.OK,self.kernel.game.purchase(user.id,self._required(payload,"listing_id"))); return
            if path == "/api/v1/conversations": self._send(HTTPStatus.CREATED,self.kernel.conversations.create(user_id=user.id,title=str(payload.get("title","New conversation")))); return
            conversation_id=self._conversation_path(path,"/chat")
            if conversation_id:
                self._ensure_chat_permissions(user.id); self._send(HTTPStatus.ACCEPTED,self.kernel.conversations.request_ai_response(conversation_id=conversation_id,user_id=user.id,prompt=self._required(payload,"prompt"),resource=str(payload.get("resource","workspace:neogen")),model=str(payload["model"]) if payload.get("model") else None)); return
            conversation_id=self._conversation_path(path,"/responses")
            if conversation_id: self._send(HTTPStatus.CREATED,self.kernel.conversations.record_ai_response(conversation_id=conversation_id,user_id=user.id,content=self._required(payload,"content"),provider=str(payload.get("provider","puter")),model=str(payload["model"]) if payload.get("model") else None)); return
            if path == "/api/v1/workspace/write": self._send(HTTPStatus.OK,self.kernel.workspace.write(self._required(payload,"path"),str(payload.get("content","")),create_parents=bool(payload.get("create_parents",True)),expected_sha256=str(payload["expected_sha256"]) if payload.get("expected_sha256") else None)); return
            if path == "/api/v1/workspace/mkdir": self._send(HTTPStatus.CREATED,self.kernel.workspace.create_directory(self._required(payload,"path"))); return
            if path == "/api/v1/workspace/delete": self._send(HTTPStatus.OK,self.kernel.workspace.delete(self._required(payload,"path"),recursive=bool(payload.get("recursive",False)))); return
            if path == "/api/v1/terminal/execute":
                command=payload.get("command")
                if not isinstance(command,list): raise ApiError(HTTPStatus.BAD_REQUEST,"command must be an argument list")
                self._send(HTTPStatus.OK,self.kernel.terminal.execute(command,cwd=str(payload.get("cwd","")),timeout_seconds=int(payload["timeout_seconds"]) if payload.get("timeout_seconds") else None,env=dict(payload.get("env",{})),stdin=str(payload["stdin"]) if payload.get("stdin") is not None else None)); return
            if path == "/api/v1/checkpoints": self._send(HTTPStatus.CREATED,self.kernel.checkpoints.save(category=self._required(payload,"category"),subject_id=str(payload.get("subject_id") or user.id),state=payload.get("state",{}),checkpoint_id=payload.get("checkpoint_id"))); return
            if path == "/api/v1/permissions/grant":
                if "admin" not in user.roles: raise ApiError(HTTPStatus.FORBIDDEN,"Admin role required")
                try: scope=PermissionScope(self._required(payload,"scope"))
                except ValueError as exc: raise ApiError(HTTPStatus.BAD_REQUEST,f"Unknown permission scope: {payload.get('scope')}") from exc
                self._send(HTTPStatus.CREATED,self.kernel.permissions.grant(subject_id=self._required(payload,"subject_id"),scope=scope,resource=self._required(payload,"resource"),granted_by=user.id)); return
            if path == "/api/v1/tools/execute": self._send(HTTPStatus.OK,self.kernel.tools.execute(ToolRequest(subject_id=user.id,tool_id=self._required(payload,"tool_id"),operation=self._required(payload,"operation"),arguments=dict(payload.get("arguments",{})),resource=str(payload.get("resource","*")),correlation_id=payload.get("correlation_id")))); return
            raise ApiError(HTTPStatus.NOT_FOUND,"Endpoint not found")
        except ApiError as exc: self._send(exc.status,{"error":str(exc)})
        except IdentityError as exc: self._send(HTTPStatus.UNAUTHORIZED,{"error":str(exc)})
        except (ConversationError,WorkspaceError,TerminalError,GameError,SubscriptionError,LegalError) as exc: self._send(HTTPStatus.BAD_REQUEST,{"error":str(exc)})
        except Exception as exc: self._send(HTTPStatus.BAD_REQUEST,{"error":f"{type(exc).__name__}: {exc}"})

    def do_PATCH(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            payload = self._read_json()
            user = self._authenticated_user()
            conversation_id = self._conversation_resource(path)
            if conversation_id:
                self._send(
                    HTTPStatus.OK,
                    self.kernel.conversations.rename(
                        conversation_id,
                        user_id=user.id,
                        title=self._required(payload, "title"),
                    ),
                )
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except ApiError as exc: self._send(exc.status, {"error": str(exc)})
        except IdentityError as exc: self._send(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        except ConversationError as exc: self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc: self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            user = self._authenticated_user()
            conversation_id = self._conversation_resource(path)
            if conversation_id:
                deleted = self.kernel.conversations.delete(conversation_id, user_id=user.id)
                self._send(HTTPStatus.OK, {"deleted": True, "conversation": deleted})
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except ApiError as exc: self._send(exc.status, {"error": str(exc)})
        except IdentityError as exc: self._send(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
        except ConversationError as exc: self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc: self._send(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:
        self.kernel.events.publish("ApiRequest",source="neogen.api",payload={"client":self.client_address[0],"message":format % args})
    def _authenticated_user(self): return self.kernel.identity.resolve(self._bearer_token())
    def _bearer_token(self) -> str:
        h=self.headers.get("Authorization","")
        if not h.startswith("Bearer ") or not h[7:].strip(): raise ApiError(HTTPStatus.UNAUTHORIZED,"Bearer token required")
        return h[7:].strip()
    def _ensure_chat_permissions(self,user_id:str)->None:
        for scope in (PermissionScope.USE_MODELS,PermissionScope.USE_NETWORK):
            if not self.kernel.permissions.check(subject_id=user_id,scope=scope,resource="workspace:neogen").allowed:
                self.kernel.permissions.grant(subject_id=user_id,scope=scope,resource="workspace:neogen",granted_by="system:chat-bootstrap")
    def _ensure_role_entitlement(self,user)->None:
        privileged_plan="owner" if "owner" in user.roles else "admin" if "admin" in user.roles else None
        if privileged_plan:
            current=self.kernel.subscriptions.current(user.id)["plan"].id
            if current != privileged_plan:
                self.kernel.subscriptions.activate(user.id,privileged_plan,provider="neogen-role")
        else:
            self.kernel.subscriptions.ensure(user.id)
    @staticmethod
    def _conversation_path(path:str,suffix:str)->str|None:
        prefix="/api/v1/conversations/"
        if not path.startswith(prefix) or not path.endswith(suffix): return None
        encoded = path[len(prefix):-len(suffix)].strip("/")
        return unquote(encoded) or None
    @staticmethod
    def _conversation_resource(path: str) -> str | None:
        prefix = "/api/v1/conversations/"
        if not path.startswith(prefix): return None
        encoded = path[len(prefix):].strip("/")
        if not encoded or "/" in encoded: return None
        return unquote(encoded)
    def _read_json(self)->dict[str,Any]:
        try: length=int(self.headers.get("Content-Length","0"))
        except ValueError as exc: raise ApiError(HTTPStatus.BAD_REQUEST,"Invalid Content-Length") from exc
        if length<=0:return {}
        if length>2_500_000:raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,"Request body exceeds 2.5 MB")
        try:value=json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise ApiError(HTTPStatus.BAD_REQUEST,"Request body must be valid JSON") from exc
        if not isinstance(value,dict):raise ApiError(HTTPStatus.BAD_REQUEST,"Request body must be a JSON object")
        return value
    def _send(self,status:HTTPStatus,value:Any)->None:
        body=json.dumps(_jsonable(value),separators=(",",":"),sort_keys=True).encode("utf-8");self.send_response(int(status));self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(body)));self._cors_headers();self.end_headers();self.wfile.write(body)
    def _cors_headers(self)->None:
        self.send_header("Access-Control-Allow-Origin","*");self.send_header("Access-Control-Allow-Headers","Authorization, Content-Type");self.send_header("Access-Control-Allow-Methods","GET, POST, PATCH, DELETE, OPTIONS")
    @staticmethod
    def _required(payload:dict[str,Any],field:str)->str:
        value=str(payload.get(field,"")).strip()
        if not value:raise ApiError(HTTPStatus.BAD_REQUEST,f"{field} is required")
        return value


def create_server(*,host:str="127.0.0.1",port:int=8080,storage_path:str|Path="neogen.db",workspace_path:str|Path="workspace",enable_puter:bool=True)->ThreadingHTTPServer:
    kernel=NeoGenKernel.build(storage_path=storage_path,workspace_path=workspace_path,enable_puter=enable_puter);handler=type("ConfiguredNeoGenApiHandler",(NeoGenApiHandler,),{"kernel":kernel});server=ThreadingHTTPServer((host,port),handler);server.daemon_threads=True;return server

def main()->None:
    parser=argparse.ArgumentParser(description="Run the NeoGen REST API");parser.add_argument("--host",default="127.0.0.1");parser.add_argument("--port",type=int,default=8080);parser.add_argument("--db",default="neogen.db");parser.add_argument("--workspace",default="workspace");parser.add_argument("--disable-puter",action="store_true");args=parser.parse_args();server=create_server(host=args.host,port=args.port,storage_path=args.db,workspace_path=args.workspace,enable_puter=not args.disable_puter)
    try: print(f"NeoGen API listening on http://{args.host}:{args.port}");server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.shutdown();server.server_close();server.RequestHandlerClass.kernel.close()

if __name__=="__main__":main()
