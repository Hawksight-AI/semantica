"""
Flow Graph Engineering

n8n-style directed graph workflows for Semantica — visual node canvases,
typed node handlers, DAG execution, and domain templates (including an
authorized bug bounty hunting flow).
"""

from .engine import FlowEngine
from .models import (
    FlowEdge,
    FlowGraph,
    FlowNode,
    FlowPort,
    FlowRun,
    FlowRunStatus,
    NodeExecutionResult,
    NodeStatus,
)
from .registry import NodeRegistry, NodeTypeSpec, get_default_registry
from .templates import FlowTemplateManager, build_bug_bounty_hunting_flow

__all__ = [
    "FlowEngine",
    "FlowEdge",
    "FlowGraph",
    "FlowNode",
    "FlowPort",
    "FlowRun",
    "FlowRunStatus",
    "FlowTemplateManager",
    "NodeExecutionResult",
    "NodeRegistry",
    "NodeStatus",
    "NodeTypeSpec",
    "build_bug_bounty_hunting_flow",
    "get_default_registry",
]
