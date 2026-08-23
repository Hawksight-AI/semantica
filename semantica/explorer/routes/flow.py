"""
Flow graph engineering API — n8n-style workflow CRUD, catalog, and execution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...flow import FlowEngine, FlowGraph, FlowTemplateManager, get_default_registry
from ...flow.templates import build_bug_bounty_hunting_flow
from ...utils.exceptions import ValidationError
from ..flow_store import get_flow_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flows", tags=["Flows"])


class FlowUpsertRequest(BaseModel):
    flow: Dict[str, Any]


class FlowExecuteRequest(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class BugBountyTemplateRequest(BaseModel):
    program_name: str = "example-program"
    in_scope: List[str] = Field(default_factory=lambda: ["*.example.com", "example.com"])
    out_of_scope: List[str] = Field(default_factory=lambda: ["blog.example.com"])
    target: str = "app.example.com"
    assets: Optional[List[Any]] = None
    finding_title: str = "Sample finding (replace with authorized research notes)"
    finding_severity: str = "medium"
    finding_description: str = ""
    evidence_text: str = ""


@router.get("/catalog")
def list_node_catalog() -> Dict[str, Any]:
    registry = get_default_registry()
    return {
        "nodes": registry.list_types(),
        "categories": registry.categories(),
    }


@router.get("/templates")
def list_flow_templates() -> Dict[str, Any]:
    manager = FlowTemplateManager()
    return {
        "templates": [manager.describe(name) for name in manager.list_templates()],
    }


@router.post("/templates/bug_bounty_hunting")
def create_bug_bounty_flow(body: BugBountyTemplateRequest) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "program_name": body.program_name,
        "in_scope": body.in_scope,
        "out_of_scope": body.out_of_scope,
        "target": body.target,
        "finding_title": body.finding_title,
        "finding_severity": body.finding_severity,
    }
    if body.assets is not None:
        kwargs["assets"] = body.assets
    if body.finding_description:
        kwargs["finding_description"] = body.finding_description
    if body.evidence_text:
        kwargs["evidence_text"] = body.evidence_text

    flow = build_bug_bounty_hunting_flow(**kwargs)
    store = get_flow_store()
    store.upsert_flow(flow)
    return flow.to_dict()


@router.get("")
@router.get("/")
def list_flows() -> Dict[str, Any]:
    store = get_flow_store()
    flows = store.list_flows()
    if not flows:
        # Seed the default bug bounty template so the canvas is never empty.
        flow = build_bug_bounty_hunting_flow()
        store.upsert_flow(flow)
        flows = [flow]
    return {"flows": [f.to_dict() for f in flows]}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = get_flow_store().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.to_dict()


@router.post("")
@router.post("/")
def upsert_flow(body: FlowUpsertRequest) -> Dict[str, Any]:
    try:
        flow = FlowGraph.from_dict(body.flow)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid flow: {exc}") from exc

    engine = FlowEngine()
    errors = engine.validate(flow)
    # Allow save even with soft issues, but reject cycles / unknown types.
    hard = [e for e in errors if "cycle" in e.lower() or "Unknown node type" in e]
    if hard:
        raise HTTPException(status_code=400, detail="; ".join(hard))

    get_flow_store().upsert_flow(flow)
    return flow.to_dict()


@router.get("/{flow_id}")
def get_flow(flow_id: str) -> Dict[str, Any]:
    if flow_id in {"catalog", "templates", "runs"}:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow = get_flow_store().get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow.to_dict()


@router.delete("/{flow_id}")
def delete_flow(flow_id: str) -> Dict[str, Any]:
    deleted = get_flow_store().delete_flow(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"deleted": True, "id": flow_id}


@router.post("/{flow_id}/execute")
def execute_flow(flow_id: str, body: FlowExecuteRequest) -> Dict[str, Any]:
    store = get_flow_store()
    flow = store.get_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    engine = FlowEngine()
    try:
        run = engine.execute(flow, context=body.context, dry_run=body.dry_run)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Flow execution failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    store.save_run(run)
    # Persist node statuses back onto the flow definition for the canvas.
    status_map = run.node_status
    for node in flow.nodes:
        if node.id in status_map:
            from ...flow.models import NodeStatus

            try:
                node.status = NodeStatus(status_map[node.id])
            except ValueError:
                pass
            node.result = run.node_results.get(node.id)
            err = run.node_results.get(node.id, {}).get("error")
            node.error = err
    store.upsert_flow(flow)
    return run.to_dict()
