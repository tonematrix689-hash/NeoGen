"""Serve the NeoGen web client and API from one local tablet process."""
from __future__ import annotations
import argparse
import mimetypes
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from genesis.api.server import NeoGenApiHandler
from genesis.services.kernel import NeoGenKernel
from genesis.services.policy_runtime import EmergencyMode

class TabletHandler(NeoGenApiHandler):
    web_root: Path

    def do_GET(self) -> None:  # noqa: N802
        path=urlparse(self.path).path
        try:
            if path=="/api/v1/agents":
                self._authenticated_user(); self._send(HTTPStatus.OK,self.kernel.agent_profiles.snapshot()); return
            if path=="/api/v1/governance/runtime":
                self._authenticated_user(); self._send(HTTPStatus.OK,self.kernel.policy_runtime.snapshot()); return
            if path=="/api/v1/governance/emergency":
                self._authenticated_user(); self._send(HTTPStatus.OK,self.kernel.policy_runtime.emergency_snapshot()); return
            if path.startswith("/api/"):
                super().do_GET(); return
            self._serve_static(path)
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST,{"error":f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        path=urlparse(self.path).path
        try:
            if path=="/api/v1/conversations":
                user=self._authenticated_user(); payload=self._read_json(); agent_id=str(payload.get("agent_id","vera"))
                profile=self.kernel.agent_profiles.get(agent_id)
                prompt=self.kernel.agent_profiles.prompt_for(agent_id,context_summary=self.kernel.agent_context_summary(user.id,agent_id))
                conversation=self.kernel.conversations.create(user_id=user.id,title=str(payload.get("title") or f"{profile.name} Session"),agent_id=agent_id,system_prompt=prompt)
                self._send(HTTPStatus.CREATED,conversation); return
            conversation_id=self._conversation_path(path,"/chat")
            if conversation_id:
                user=self._authenticated_user(); payload=self._read_json(); conversation=self.kernel.conversations.get(conversation_id,user_id=user.id)
                profile=self.kernel.agent_profiles.get(conversation.agent_id)
                self._ensure_chat_permissions(user.id)
                result=self.kernel.conversations.request_ai_response(
                    conversation_id=conversation_id,user_id=user.id,prompt=self._required(payload,"prompt"),
                    resource=str(payload.get("resource","workspace:neogen")),model=str(payload["model"]) if payload.get("model") else None,
                    agent_id=profile.id,system_prompt=self.kernel.agent_profiles.prompt_for(profile.id,context_summary=self.kernel.agent_context_summary(user.id,profile.id)),
                    context=self.kernel.assistant_context(user.id))
                self.kernel.policy_runtime.record_audit(user_id=user.id,agent_id=profile.id,tool_id="puter.ai",permission="models.use",action="conversation.chat",result="prepared",risk_level=profile.risk_level,approval_status="granted",session_id=conversation_id)
                self._send(HTTPStatus.ACCEPTED,result); return
            conversation_id=self._conversation_path(path,"/responses")
            if conversation_id:
                user=self._authenticated_user(); payload=self._read_json(); conversation=self.kernel.conversations.get(conversation_id,user_id=user.id)
                message=self.kernel.conversations.record_ai_response(conversation_id=conversation_id,user_id=user.id,content=self._required(payload,"content"),provider=str(payload.get("provider","puter")),model=str(payload["model"]) if payload.get("model") else None,agent_id=conversation.agent_id)
                self._send(HTTPStatus.CREATED,message); return
            if path=="/api/v1/governance/emergency":
                user=self._authenticated_user(); payload=self._read_json()
                if not any(role in {"admin","administrator","organization_admin"} for role in user.roles):
                    self._send(HTTPStatus.FORBIDDEN,{"error":"Administrator role required"}); return
                state=self.kernel.policy_runtime.set_emergency_mode(EmergencyMode(self._required(payload,"mode")))
                self.kernel.policy_runtime.record_audit(user_id=user.id,permission="governance.emergency",action="emergency.mode",result=state["mode"],risk_level=4,approval_status="administrator",session_id=None)
                self._send(HTTPStatus.OK,state); return
            super().do_POST()
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST,{"error":f"{type(exc).__name__}: {exc}"})

    @staticmethod
    def _conversation_path(path:str,suffix:str)->str|None:
        prefix="/api/v1/conversations/"
        if not path.startswith(prefix) or not path.endswith(suffix): return None
        return unquote(path[len(prefix):-len(suffix)].strip("/")) or None

    def _serve_static(self,request_path:str)->None:
        relative=request_path.lstrip("/") or "index.html"; target=(self.web_root/relative).resolve()
        try: target.relative_to(self.web_root)
        except ValueError: self.send_error(HTTPStatus.FORBIDDEN); return
        if target.is_dir(): target=target/"index.html"
        if not target.is_file(): target=self.web_root/"index.html"
        try: body=target.read_bytes()
        except OSError: self.send_error(HTTPStatus.NOT_FOUND); return
        if target.name=="index.html":
            text=body.decode("utf-8").replace('value="http://127.0.0.1:8080/api/v1"','value="/api/v1"')
            text=text.replace("function apiBase(){return $('apiBase').value.replace(/\\/$/,'')}","function apiBase(){const v=$('apiBase').value.trim();return (v&&v!=='/api/v1'?v:location.origin+'/api/v1').replace(/\\/$/,'')}")
            text=text.replace("const $=id=>document.getElementById(id);","if('serviceWorker' in navigator){navigator.serviceWorker.getRegistrations().then(rs=>rs.forEach(r=>r.unregister()));}const $=id=>document.getElementById(id);")
            for asset,tag,anchor in [
                ("/neogen-preview.css?v=2",'<link rel="stylesheet" href="/neogen-preview.css?v=2">',"</head>"),
                ("/neogen-preview.js?v=2",'<script src="/neogen-preview.js?v=2"></script>',"</body>"),
                ("/neogen-agents.js?v=1",'<script src="/neogen-agents.js?v=1"></script>',"</body>")]:
                if asset not in text:text=text.replace(anchor,f"{tag}{anchor}")
            body=text.encode("utf-8")
        content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store, max-age=0"); self.end_headers(); self.wfile.write(body)

def create_tablet_server(*,host:str="127.0.0.1",port:int=8080,storage_path:str|Path="neogen.db",workspace_path:str|Path="workspace",web_path:str|Path|None=None)->ThreadingHTTPServer:
    kernel=NeoGenKernel.build(storage_path=storage_path,workspace_path=workspace_path,enable_puter=True)
    root=(Path(web_path) if web_path else Path(__file__).resolve().parent.parent/"web").resolve()
    handler=type("ConfiguredTabletHandler",(TabletHandler,),{"kernel":kernel,"web_root":root})
    server=ThreadingHTTPServer((host,port),handler); server.daemon_threads=True; return server

def main()->None:
    parser=argparse.ArgumentParser(description="Run NeoGen locally on an Android tablet"); parser.add_argument("--host",default="127.0.0.1"); parser.add_argument("--port",type=int,default=8080); parser.add_argument("--db",default="neogen.db"); parser.add_argument("--workspace",default="workspace"); parser.add_argument("--web",default=None); args=parser.parse_args()
    server=create_tablet_server(host=args.host,port=args.port,storage_path=args.db,workspace_path=args.workspace,web_path=args.web)
    try: print(f"NeoGen tablet server: http://{args.host}:{args.port}/"); server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.shutdown(); server.server_close(); server.RequestHandlerClass.kernel.close()
if __name__=="__main__": main()
