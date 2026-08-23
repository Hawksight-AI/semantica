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
from .integrations import DEFAULT_VERIFIABLE_RULES
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
    "DEFAULT_VERIFIABLE_RULES",
    "build_bug_bounty_hunting_flow",
    "get_default_registry",
]
