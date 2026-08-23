"""
Flow execution engine — topological DAG runner for n8n-style graphs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from .models import FlowGraph, FlowRun, FlowRunStatus, NodeStatus
from .registry import NodeRegistry, get_default_registry


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FlowEngine:
    """
    Execute a FlowGraph in dependency order.

    Upstream node outputs are merged into each node's input bag under the
    predecessor node id, plus a flattened ``inputs`` view for convenience.
    """

    def __init__(self, registry: Optional[NodeRegistry] = None):
        self.logger = get_logger("flow_engine")
        self.registry = registry or get_default_registry()

    def validate(self, flow: FlowGraph) -> List[str]:
        """Return validation errors (empty list means valid)."""
        errors: List[str] = []
        node_ids = {n.id for n in flow.nodes}

        if not flow.nodes:
            errors.append("Flow has no nodes")

        for node in flow.nodes:
            if not self.registry.get(node.type):
                errors.append(f"Unknown node type '{node.type}' on node '{node.id}'")

        for edge in flow.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge {edge.id} source '{edge.source}' missing")
            if edge.target not in node_ids:
                errors.append(f"Edge {edge.id} target '{edge.target}' missing")

        try:
            self._topological_order(flow)
        except ValidationError as exc:
            errors.append(str(exc))

        return errors

    def _topological_order(self, flow: FlowGraph) -> List[str]:
        indegree: Dict[str, int] = {n.id: 0 for n in flow.nodes}
        adj: Dict[str, List[str]] = {n.id: [] for n in flow.nodes}
        for edge in flow.edges:
            if edge.source in adj and edge.target in indegree:
                adj[edge.source].append(edge.target)
                indegree[edge.target] += 1

        queue = [nid for nid, deg in indegree.items() if deg == 0]
        order: List[str] = []
        while queue:
            queue.sort()
            current = queue.pop(0)
            order.append(current)
            for nxt in adj[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        if len(order) != len(flow.nodes):
            raise ValidationError("Flow graph contains a cycle")
        return order

    def execute(
        self,
        flow: FlowGraph,
        context: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> FlowRun:
        """Run the flow and return a FlowRun with per-node results."""
        errors = self.validate(flow)
        if errors:
            raise ValidationError("; ".join(errors))

        run = FlowRun(
            id=str(uuid4()),
            flow_id=flow.id,
            status=FlowRunStatus.RUNNING,
            context=dict(context or {}),
            started_at=_utcnow(),
        )
        run.context.setdefault("dry_run", dry_run)
        run.context.setdefault("graph_nodes", [])
        run.context.setdefault("graph_edges", [])
        run.context.setdefault("findings", [])
        run.context.setdefault("decisions", [])

        node_map = flow.node_map()
        order = self._topological_order(flow)
        skip: set = set()

        try:
            for node_id in order:
                node = node_map[node_id]
                if node_id in skip:
                    node.status = NodeStatus.SKIPPED
                    run.node_status[node_id] = NodeStatus.SKIPPED.value
                    continue

                preds = flow.predecessors(node_id)
                pred_statuses = [run.node_status.get(p) for p in preds]
                if any(
                    status in (NodeStatus.FAILED.value, NodeStatus.SKIPPED.value)
                    for status in pred_statuses
                ):
                    node.status = NodeStatus.SKIPPED
                    run.node_status[node_id] = NodeStatus.SKIPPED.value
                    continue

                upstream: Dict[str, Any] = {}
                flat_inputs: Dict[str, Any] = {}
                for pred in preds:
                    pred_out = run.node_results.get(pred, {}).get("output", {})
                    upstream[pred] = pred_out
                    if isinstance(pred_out, dict):
                        flat_inputs.update(pred_out)

                node.status = NodeStatus.RUNNING
                run.node_status[node_id] = NodeStatus.RUNNING.value
                self.logger.info("Executing flow node %s (%s)", node.id, node.type)

                try:
                    spec = self.registry.require(node.type)
                    result = spec.handler(node, {"upstream": upstream, "inputs": flat_inputs}, run.context)
                    node.status = NodeStatus.SUCCESS
                    node.result = result.to_dict()
                    run.node_status[node_id] = NodeStatus.SUCCESS.value
                    run.node_results[node_id] = result.to_dict()
                    if result.skip_downstream:
                        for succ in flow.successors(node_id):
                            skip.add(succ)
                except Exception as exc:
                    self.logger.exception("Flow node %s failed", node_id)
                    node.status = NodeStatus.FAILED
                    node.error = str(exc)
                    run.node_status[node_id] = NodeStatus.FAILED.value
                    run.node_results[node_id] = {"error": str(exc)}
                    run.status = FlowRunStatus.FAILED
                    run.error = f"Node '{node.label}' ({node_id}) failed: {exc}"
                    run.finished_at = _utcnow()
                    return run

            run.status = FlowRunStatus.SUCCESS
            run.finished_at = _utcnow()
            return run
        except Exception as exc:
            run.status = FlowRunStatus.FAILED
            run.error = str(exc)
            run.finished_at = _utcnow()
            raise ProcessingError(f"Flow execution failed: {exc}") from exc
