"""
In-memory flow store for Explorer API sessions.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ...flow.models import FlowGraph, FlowRun


class FlowStore:
    """Process-local store for flow definitions and runs."""

    def __init__(self) -> None:
        self.flows: Dict[str, FlowGraph] = {}
        self.runs: Dict[str, FlowRun] = {}

    def upsert_flow(self, flow: FlowGraph) -> FlowGraph:
        self.flows[flow.id] = flow
        return flow

    def get_flow(self, flow_id: str) -> Optional[FlowGraph]:
        return self.flows.get(flow_id)

    def list_flows(self) -> List[FlowGraph]:
        return list(self.flows.values())

    def delete_flow(self, flow_id: str) -> bool:
        return self.flows.pop(flow_id, None) is not None

    def save_run(self, run: FlowRun) -> FlowRun:
        self.runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> Optional[FlowRun]:
        return self.runs.get(run_id)

    def list_runs(self, flow_id: Optional[str] = None) -> List[FlowRun]:
        runs = list(self.runs.values())
        if flow_id:
            runs = [r for r in runs if r.flow_id == flow_id]
        return runs


_STORE: Optional[FlowStore] = None


def get_flow_store() -> FlowStore:
    global _STORE
    if _STORE is None:
        _STORE = FlowStore()
    return _STORE
