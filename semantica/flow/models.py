"""
Flow graph models for n8n-style workflow engineering.

Nodes form a directed acyclic graph. Each node has a type, position
(for canvas layout), configuration, and optional typed connections.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class NodeStatus(str, Enum):
    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class FlowRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FlowPort:
    """Typed connection port on a flow node."""

    id: str
    label: str
    direction: str = "output"  # input | output
    data_type: str = "any"


@dataclass
class FlowNode:
    """Single node in an n8n-style flow graph."""

    id: str
    type: str
    label: str
    config: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    status: NodeStatus = NodeStatus.IDLE
    category: str = "general"
    description: str = ""
    ports: List[FlowPort] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowNode":
        ports = [FlowPort(**p) if isinstance(p, dict) else p for p in data.get("ports", [])]
        status = data.get("status", NodeStatus.IDLE)
        if isinstance(status, str):
            status = NodeStatus(status)
        return cls(
            id=data["id"],
            type=data["type"],
            label=data.get("label", data["type"]),
            config=dict(data.get("config") or {}),
            position=dict(data.get("position") or {"x": 0.0, "y": 0.0}),
            status=status,
            category=data.get("category", "general"),
            description=data.get("description", ""),
            ports=ports,
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class FlowEdge:
    """Directed edge between two flow nodes (source → target)."""

    id: str
    source: str
    target: str
    source_port: str = "out"
    target_port: str = "in"
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowEdge":
        return cls(
            id=data.get("id") or f"e_{data['source']}_{data['target']}",
            source=data["source"],
            target=data["target"],
            source_port=data.get("source_port", "out"),
            target_port=data.get("target_port", "in"),
            label=data.get("label", ""),
        )


@dataclass
class FlowGraph:
    """n8n-style workflow definition as a node/edge graph."""

    id: str
    name: str
    description: str = ""
    nodes: List[FlowNode] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowGraph":
        return cls(
            id=data.get("id") or str(uuid4()),
            name=data.get("name", "untitled"),
            description=data.get("description", ""),
            nodes=[FlowNode.from_dict(n) for n in data.get("nodes", [])],
            edges=[FlowEdge.from_dict(e) for e in data.get("edges", [])],
            metadata=dict(data.get("metadata") or {}),
            version=data.get("version", "1.0.0"),
        )

    def node_map(self) -> Dict[str, FlowNode]:
        return {n.id: n for n in self.nodes}

    def predecessors(self, node_id: str) -> List[str]:
        return [e.source for e in self.edges if e.target == node_id]

    def successors(self, node_id: str) -> List[str]:
        return [e.target for e in self.edges if e.source == node_id]


@dataclass
class NodeExecutionResult:
    """Result produced by a single node handler."""

    output: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)
    skip_downstream: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FlowRun:
    """One execution of a flow graph."""

    id: str
    flow_id: str
    status: FlowRunStatus = FlowRunStatus.PENDING
    context: Dict[str, Any] = field(default_factory=dict)
    node_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    node_status: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "status": self.status.value,
            "context": self.context,
            "node_results": self.node_results,
            "node_status": self.node_status,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
