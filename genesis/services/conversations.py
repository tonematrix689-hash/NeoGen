"""Persistent governed NeoGen conversations."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from .events import EventBus
from .storage import SQLiteStore, StorageError
from .tools import ToolRegistry, ToolRequest

class ConversationError(RuntimeError): pass

@dataclass(frozen=True, slots=True)
class Conversation:
    id:str; user_id:str; title:str; agent_id:str; created_at:datetime; updated_at:datetime

@dataclass(frozen=True, slots=True)
class Message:
    id:str; conversation_id:str; role:str; content:str; created_at:datetime; metadata:dict[str,Any]

class ConversationService:
    conversation_namespace="vera.conversations"; message_namespace="vera.messages"
    def __init__(self,store:SQLiteStore,tools:ToolRegistry,events:EventBus|None=None)->None:
        self._store=store; self._tools=tools; self._events=events or EventBus()
    def create(self,*,user_id:str,title:str="New conversation",agent_id:str="vera",system_prompt:str|None=None)->Conversation:
        now=datetime.now(timezone.utc); c=Conversation(f"conversation:{uuid4()}",self._required(user_id,"user_id"),self._required(title,"title"),self._required(agent_id,"agent_id"),now,now)
        self._store.put(self.conversation_namespace,c.id,self._conversation_payload(c))
        if system_prompt:self.add_message(conversation_id=c.id,user_id=user_id,role="system",content=system_prompt,metadata={"agent_id":agent_id})
        self._events.publish("ConversationCreated",source="neogen.vera",payload={"conversation_id":c.id,"title":c.title,"agent_id":agent_id},user_id=user_id); return c
    def get(self,conversation_id:str,*,user_id:str)->Conversation:
        try:r=self._store.get(self.conversation_namespace,conversation_id).value
        except StorageError as exc:raise ConversationError(f"Unknown conversation: {conversation_id}") from exc
        c=self._conversation_from_payload(r); self._assert_owner(c,user_id); return c
    def list(self,*,user_id:str)->tuple[Conversation,...]:
        items=[self._conversation_from_payload(r.value) for r in self._store.list(self.conversation_namespace)]
        return tuple(sorted((x for x in items if x.user_id==user_id),key=lambda x:x.updated_at,reverse=True))
    def messages(self,conversation_id:str,*,user_id:str)->tuple[Message,...]:
        self.get(conversation_id,user_id=user_id); prefix=f"{conversation_id}:"
        items=[self._message_from_payload(r.value) for r in self._store.list(self.message_namespace,prefix=prefix)]
        return tuple(sorted(items,key=lambda x:x.created_at))
    def add_message(self,*,conversation_id:str,user_id:str,role:str,content:str,metadata:dict[str,Any]|None=None)->Message:
        c=self.get(conversation_id,user_id=user_id); role=self._required(role,"role").lower()
        if role not in {"system","user","assistant","tool"}:raise ConversationError(f"Unsupported message role: {role}")
        now=datetime.now(timezone.utc); m=Message(f"message:{uuid4()}",conversation_id,role,self._required(content,"content"),now,dict(metadata or {}))
        self._store.put(self.message_namespace,f"{conversation_id}:{now.timestamp():020.6f}:{m.id}",self._message_payload(m))
        current=self._store.get(self.conversation_namespace,c.id); updated=Conversation(c.id,c.user_id,c.title,c.agent_id,c.created_at,now)
        self._store.put(self.conversation_namespace,c.id,self._conversation_payload(updated),expected_version=current.version)
        self._events.publish("ConversationMessageAdded",source="neogen.vera",payload={"conversation_id":conversation_id,"message_id":m.id,"role":role,"agent_id":c.agent_id},user_id=user_id); return m
    def request_ai_response(self,*,conversation_id:str,user_id:str,prompt:str,resource:str="workspace:neogen",model:str|None=None,agent_id:str|None=None,system_prompt:str|None=None,context:dict[str,Any]|None=None)->dict[str,Any]:
        c=self.get(conversation_id,user_id=user_id); selected=agent_id or c.agent_id
        if selected!=c.agent_id: raise ConversationError("Selected agent does not match conversation agent")
        self.add_message(conversation_id=conversation_id,user_id=user_id,role="user",content=prompt,metadata={"agent_id":selected})
        history=[{"role":m.role,"content":m.content} for m in self.messages(conversation_id,user_id=user_id) if m.role in {"system","user","assistant"}]
        if system_prompt and not any(m["role"]=="system" for m in history): history.insert(0,{"role":"system","content":system_prompt})
        args={"messages":history,"agent_id":selected,"context":context or {}}
        if model:args["model"]=model
        result=self._tools.execute(ToolRequest(subject_id=user_id,tool_id="puter.ai",operation="ai.chat",arguments=args,resource=resource,correlation_id=conversation_id))
        return {"conversation_id":conversation_id,"agent_id":selected,"execution":result,"status":"browser_execution_required"}
    def record_ai_response(self,*,conversation_id:str,user_id:str,content:str,provider:str="puter",model:str|None=None,agent_id:str|None=None)->Message:
        c=self.get(conversation_id,user_id=user_id); selected=agent_id or c.agent_id; md={"provider":provider,"agent_id":selected}
        if model:md["model"]=model
        return self.add_message(conversation_id=conversation_id,user_id=user_id,role="assistant",content=content,metadata=md)
    def stats(self)->dict[str,int]:return {"conversations":len(self._store.list(self.conversation_namespace)),"messages":len(self._store.list(self.message_namespace))}
    @staticmethod
    def _assert_owner(c:Conversation,user_id:str)->None:
        if c.user_id!=user_id:raise ConversationError("Conversation access denied")
    @staticmethod
    def _required(v:str,f:str)->str:
        v=v.strip()
        if not v:raise ConversationError(f"{f} is required")
        return v
    @staticmethod
    def _conversation_payload(v:Conversation)->dict[str,Any]:return {"id":v.id,"user_id":v.user_id,"title":v.title,"agent_id":v.agent_id,"created_at":v.created_at.isoformat(),"updated_at":v.updated_at.isoformat()}
    @staticmethod
    def _conversation_from_payload(v:dict[str,Any])->Conversation:return Conversation(str(v["id"]),str(v["user_id"]),str(v["title"]),str(v.get("agent_id","vera")),datetime.fromisoformat(str(v["created_at"])),datetime.fromisoformat(str(v["updated_at"])))
    @staticmethod
    def _message_payload(v:Message)->dict[str,Any]:return {"id":v.id,"conversation_id":v.conversation_id,"role":v.role,"content":v.content,"created_at":v.created_at.isoformat(),"metadata":v.metadata}
    @staticmethod
    def _message_from_payload(v:dict[str,Any])->Message:return Message(str(v["id"]),str(v["conversation_id"]),str(v["role"]),str(v["content"]),datetime.fromisoformat(str(v["created_at"])),dict(v.get("metadata",{})))
