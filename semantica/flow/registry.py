"""
Node type registry for flow graph engineering.

Handlers are pure callables: (node, upstream_outputs, run_context) → NodeExecutionResult.
They must not perform unauthorized network attacks or exploit generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import FlowNode, NodeExecutionResult

NodeHandler = Callable[[FlowNode, Dict[str, Any], Dict[str, Any]], NodeExecutionResult]


@dataclass
class NodeTypeSpec:
    """Catalog entry describing a reusable flow node type."""

    type: str
    label: str
    category: str
    description: str
    handler: NodeHandler
    default_config: Dict[str, Any] = field(default_factory=dict)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    color: str = "#4aa3ff"

    def to_catalog_entry(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "category": self.category,
            "description": self.description,
            "default_config": self.default_config,
            "config_schema": self.config_schema,
            "color": self.color,
        }


class NodeRegistry:
    """Global registry of flow node types."""

    def __init__(self) -> None:
        self._types: Dict[str, NodeTypeSpec] = {}

    def register(self, spec: NodeTypeSpec) -> None:
        self._types[spec.type] = spec

    def get(self, node_type: str) -> Optional[NodeTypeSpec]:
        return self._types.get(node_type)

    def require(self, node_type: str) -> NodeTypeSpec:
        spec = self.get(node_type)
        if spec is None:
            raise KeyError(f"Unknown flow node type: {node_type}")
        return spec

    def list_types(self) -> List[Dict[str, Any]]:
        return [spec.to_catalog_entry() for spec in self._types.values()]

    def categories(self) -> List[str]:
        return sorted({spec.category for spec in self._types.values()})


_DEFAULT_REGISTRY: Optional[NodeRegistry] = None


def get_default_registry() -> NodeRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from .nodes import register_builtin_nodes

        _DEFAULT_REGISTRY = NodeRegistry()
        register_builtin_nodes(_DEFAULT_REGISTRY)
    return _DEFAULT_REGISTRY
