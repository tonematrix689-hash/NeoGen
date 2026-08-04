"""Project graph, dependency analysis, decisions, and change intelligence for NeoGen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Iterable
from uuid import uuid4


class ProjectIntelligenceError(RuntimeError):
    """Base error for project intelligence operations."""


class NodeKind(StrEnum):
    PROJECT = "project"
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    API = "api"
    TEST = "test"
    DOCUMENT = "document"
    DEPENDENCY = "dependency"
    ISSUE = "issue"
    TODO = "todo"
    BUILD = "build"
    DECISION = "decision"


class RelationKind(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    DEPENDS_ON = "depends_on"
    TESTS = "tests"
    DOCUMENTS = "documents"
    IMPLEMENTS = "implements"
    REFERENCES = "references"
    SUPERSEDES = "supersedes"
    AFFECTS = "affects"


@dataclass(frozen=True, slots=True)
class ProjectNode:
    id: str
    project_id: str
    kind: NodeKind
    name: str
    path: str | None
    metadata: dict[str, str]
    tags: frozenset[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectRelation:
    id: str
    project_id: str
    source_id: str
    target_id: str
    kind: RelationKind
    metadata: dict[str, str]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ArchitectureDecision:
    id: str
    project_id: str
    title: str
    context: str
    decision: str
    consequences: str
    status: str
    related_nodes: frozenset[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    project_id: str
    name: str
    nodes: int
    relations: int
    decisions: int
    files: int
    tests: int
    issues: int
    todos: int
    build_status: str
    updated_at: datetime


class ProjectIntelligence:
    """Thread-safe project knowledge graph and decision registry."""

    def __init__(self) -> None:
        self._projects: dict[str, str] = {}
        self._nodes: dict[str, ProjectNode] = {}
        self._relations: dict[str, ProjectRelation] = {}
        self._decisions: dict[str, ArchitectureDecision] = {}
        self._build_status: dict[str, str] = {}
        self._lock = RLock()

    def create_project(self, name: str) -> ProjectNode:
        project_id = f"project:{uuid4()}"
        now = datetime.now(timezone.utc)
        node = ProjectNode(
            id=project_id,
            project_id=project_id,
            kind=NodeKind.PROJECT,
            name=self._required(name, "name"),
            path=None,
            metadata={},
            tags=frozenset(),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._projects[project_id] = node.name
            self._nodes[node.id] = node
            self._build_status[project_id] = "unknown"
        return node

    def add_node(
        self,
        *,
        project_id: str,
        kind: NodeKind,
        name: str,
        path: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] = (),
    ) -> ProjectNode:
        self._require_project(project_id)
        now = datetime.now(timezone.utc)
        node = ProjectNode(
            id=f"node:{uuid4()}",
            project_id=project_id,
            kind=kind,
            name=self._required(name, "name"),
            path=self._optional(path),
            metadata=dict(metadata or {}),
            tags=self._normalize(tags),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._nodes[node.id] = node
        return node

    def update_node(
        self,
        node_id: str,
        *,
        name: str | None = None,
        path: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: Iterable[str] | None = None,
    ) -> ProjectNode:
        with self._lock:
            node = self.get_node(node_id)
            updated = replace(
                node,
                name=node.name if name is None else self._required(name, "name"),
                path=node.path if path is None else self._optional(path),
                metadata=node.metadata if metadata is None else dict(metadata),
                tags=node.tags if tags is None else self._normalize(tags),
                updated_at=datetime.now(timezone.utc),
            )
            self._nodes[node_id] = updated
            return updated

    def relate(
        self,
        *,
        source_id: str,
        target_id: str,
        kind: RelationKind,
        metadata: dict[str, str] | None = None,
    ) -> ProjectRelation:
        source = self.get_node(source_id)
        target = self.get_node(target_id)
        if source.project_id != target.project_id:
            raise ProjectIntelligenceError("Cross-project relations are not supported")
        relation = ProjectRelation(
            id=f"relation:{uuid4()}",
            project_id=source.project_id,
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            metadata=dict(metadata or {}),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._relations[relation.id] = relation
        return relation

    def record_decision(
        self,
        *,
        project_id: str,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        status: str = "accepted",
        related_nodes: Iterable[str] = (),
    ) -> ArchitectureDecision:
        self._require_project(project_id)
        related = frozenset(related_nodes)
        for node_id in related:
            node = self.get_node(node_id)
            if node.project_id != project_id:
                raise ProjectIntelligenceError("Decision references another project")
        now = datetime.now(timezone.utc)
        item = ArchitectureDecision(
            id=f"decision:{uuid4()}",
            project_id=project_id,
            title=self._required(title, "title"),
            context=self._required(context, "context"),
            decision=self._required(decision, "decision"),
            consequences=self._required(consequences, "consequences"),
            status=self._required(status, "status"),
            related_nodes=related,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._decisions[item.id] = item
        return item

    def set_build_status(self, project_id: str, status: str) -> None:
        self._require_project(project_id)
        with self._lock:
            self._build_status[project_id] = self._required(status, "status")

    def get_node(self, node_id: str) -> ProjectNode:
        with self._lock:
            try:
                return self._nodes[node_id]
            except KeyError as exc:
                raise ProjectIntelligenceError(f"Unknown node: {node_id}") from exc

    def nodes(
        self,
        project_id: str,
        *,
        kind: NodeKind | None = None,
        text: str | None = None,
        tags: Iterable[str] = (),
    ) -> tuple[ProjectNode, ...]:
        self._require_project(project_id)
        query = "" if text is None else text.strip().lower()
        required_tags = self._normalize(tags)
        with self._lock:
            matches = [
                node
                for node in self._nodes.values()
                if node.project_id == project_id
                and (kind is None or node.kind is kind)
                and required_tags.issubset(node.tags)
                and (
                    not query
                    or query in node.name.lower()
                    or (node.path is not None and query in node.path.lower())
                    or any(query in value.lower() for value in node.metadata.values())
                )
            ]
        matches.sort(key=lambda item: (item.kind.value, item.name.lower()))
        return tuple(matches)

    def dependencies(self, node_id: str, *, recursive: bool = False) -> tuple[ProjectNode, ...]:
        self.get_node(node_id)
        visited: set[str] = set()
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for relation in self._relations.values():
                if relation.source_id != current or relation.kind not in {
                    RelationKind.DEPENDS_ON,
                    RelationKind.IMPORTS,
                    RelationKind.CALLS,
                }:
                    continue
                if relation.target_id in visited:
                    continue
                visited.add(relation.target_id)
                if recursive:
                    frontier.append(relation.target_id)
        return tuple(self._nodes[item] for item in visited)

    def dependents(self, node_id: str, *, recursive: bool = False) -> tuple[ProjectNode, ...]:
        self.get_node(node_id)
        visited: set[str] = set()
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for relation in self._relations.values():
                if relation.target_id != current or relation.kind not in {
                    RelationKind.DEPENDS_ON,
                    RelationKind.IMPORTS,
                    RelationKind.CALLS,
                }:
                    continue
                if relation.source_id in visited:
                    continue
                visited.add(relation.source_id)
                if recursive:
                    frontier.append(relation.source_id)
        return tuple(self._nodes[item] for item in visited)

    def unused_files(self, project_id: str) -> tuple[ProjectNode, ...]:
        files = self.nodes(project_id, kind=NodeKind.FILE)
        referenced = {
            relation.target_id
            for relation in self._relations.values()
            if relation.project_id == project_id
            and relation.kind in {
                RelationKind.IMPORTS,
                RelationKind.DEPENDS_ON,
                RelationKind.REFERENCES,
                RelationKind.TESTS,
            }
        }
        return tuple(node for node in files if node.id not in referenced)

    def tests_for(self, node_id: str) -> tuple[ProjectNode, ...]:
        self.get_node(node_id)
        test_ids = {
            relation.source_id
            for relation in self._relations.values()
            if relation.target_id == node_id and relation.kind is RelationKind.TESTS
        }
        return tuple(self._nodes[item] for item in test_ids)

    def decisions(self, project_id: str, *, text: str | None = None) -> tuple[ArchitectureDecision, ...]:
        self._require_project(project_id)
        query = "" if text is None else text.strip().lower()
        with self._lock:
            items = [
                item
                for item in self._decisions.values()
                if item.project_id == project_id
                and (
                    not query
                    or query in item.title.lower()
                    or query in item.context.lower()
                    or query in item.decision.lower()
                    or query in item.consequences.lower()
                )
            ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return tuple(items)

    def snapshot(self, project_id: str) -> ProjectSnapshot:
        self._require_project(project_id)
        project_nodes = self.nodes(project_id)
        project_relations = tuple(
            relation for relation in self._relations.values() if relation.project_id == project_id
        )
        decisions = tuple(
            decision for decision in self._decisions.values() if decision.project_id == project_id
        )
        return ProjectSnapshot(
            project_id=project_id,
            name=self._projects[project_id],
            nodes=len(project_nodes),
            relations=len(project_relations),
            decisions=len(decisions),
            files=sum(1 for node in project_nodes if node.kind is NodeKind.FILE),
            tests=sum(1 for node in project_nodes if node.kind is NodeKind.TEST),
            issues=sum(1 for node in project_nodes if node.kind is NodeKind.ISSUE),
            todos=sum(1 for node in project_nodes if node.kind is NodeKind.TODO),
            build_status=self._build_status[project_id],
            updated_at=datetime.now(timezone.utc),
        )

    def _require_project(self, project_id: str) -> None:
        with self._lock:
            if project_id not in self._projects:
                raise ProjectIntelligenceError(f"Unknown project: {project_id}")

    @staticmethod
    def _required(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ProjectIntelligenceError(f"{field} is required")
        return cleaned

    @staticmethod
    def _optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _normalize(values: Iterable[str]) -> frozenset[str]:
        return frozenset(value.strip().lower() for value in values if value.strip())
