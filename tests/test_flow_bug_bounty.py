"""Tests for n8n-style flow graph engineering and bug bounty hunting template."""

from __future__ import annotations

import pytest

from semantica.flow import (
    DEFAULT_VERIFIABLE_RULES,
    FlowEngine,
    FlowGraph,
    FlowNode,
    FlowEdge,
    FlowTemplateManager,
    build_bug_bounty_hunting_flow,
    get_default_registry,
)
from semantica.pipeline import PipelineTemplateManager
from semantica.utils.exceptions import ValidationError


def test_registry_includes_bug_bounty_nodes():
    registry = get_default_registry()
    types = {entry["type"] for entry in registry.list_types()}
    assert "program_scope" in types
    assert "scope_check" in types
    assert "finding_record" in types
    assert "submission_gate" in types
    assert "verifiable_rules" in types
    assert "self_verify" in types
    assert "ship_loop" in types
    assert "bug_bounty" in registry.categories()
    assert "agent_os" in registry.categories()


def test_bug_bounty_template_structure():
    flow = build_bug_bounty_hunting_flow()
    assert flow.name == "Bug Bounty Hunting"
    assert len(flow.nodes) >= 10
    assert len(flow.edges) >= 9
    assert flow.metadata.get("authorized_only") is True
    engine = FlowEngine()
    assert engine.validate(flow) == []


def test_bug_bounty_flow_executes_successfully():
    flow = build_bug_bounty_hunting_flow(
        program_name="test-bb",
        in_scope=["*.example.com", "example.com"],
        out_of_scope=["blog.example.com"],
        target="app.example.com",
    )
    run = FlowEngine().execute(flow)
    assert run.status.value == "success"
    assert run.context.get("scope")
    assert run.context.get("assets")
    assert run.context.get("findings")
    assert run.context.get("report")
    assert run.context.get("submission_gate", {}).get("ready") is True
    assert run.context.get("exported_graph", {}).get("nodes")
    assert run.context.get("verification", {}).get("accepted") is True
    assert run.context.get("verifiable_rules", {}).get("passed") is True
    assert run.context.get("ship_loop", {}).get("source") == "cyrilxbt/24h-ship"
    assert len(DEFAULT_VERIFIABLE_RULES) == 8


def test_scope_gate_blocks_out_of_scope_target():
    flow = build_bug_bounty_hunting_flow(
        program_name="test-bb",
        in_scope=["app.example.com"],
        out_of_scope=[],
        target="evil.example.net",
    )
    run = FlowEngine().execute(flow)
    # Scope check should fail-closed and skip downstream; overall run still succeeds.
    assert run.node_status.get("n_scope_check") == "success"
    assert run.node_results["n_scope_check"]["output"]["in_scope"] is False
    assert run.node_status.get("n_assets") == "skipped"
    assert run.status.value == "success"


def test_flow_rejects_cycles():
    flow = FlowGraph(
        id="cyclic",
        name="cyclic",
        nodes=[
            FlowNode(id="a", type="trigger", label="A"),
            FlowNode(id="b", type="merge", label="B"),
        ],
        edges=[
            FlowEdge(id="e1", source="a", target="b"),
            FlowEdge(id="e2", source="b", target="a"),
        ],
    )
    with pytest.raises(ValidationError):
        FlowEngine().execute(flow)


def test_flow_template_manager():
    manager = FlowTemplateManager()
    assert "bug_bounty_hunting" in manager.list_templates()
    info = manager.describe("bug_bounty_hunting")
    assert info["node_count"] > 0
    graph = manager.get_template_graph("bug_bounty_hunting")
    assert graph["name"] == "Bug Bounty Hunting"


def test_pipeline_template_includes_bug_bounty():
    manager = PipelineTemplateManager()
    assert "bug_bounty_hunting" in manager.list_templates()
    template = manager.get_template("bug_bounty_hunting")
    assert template is not None
    assert template.metadata.get("style") == "n8n_graph"
    assert any(step["name"] == "submission_gate" for step in template.steps)


def test_submission_gate_rejected_only_fails():
    from semantica.flow.nodes import handle_submission_gate

    node = FlowNode(id="g", type="submission_gate", label="Gate")
    context = {
        "report": {"id": "r1", "title": "t"},
        "findings": [{"id": "f1", "title": "dup", "triage_action": "reject"}],
        "triaged_findings": [{"id": "f1", "title": "dup", "triage_action": "reject"}],
        "scope": {"in_scope": ["example.com"]},
        "evidence": [{"id": "e1"}],
        "scope_violations": [],
    }
    result = handle_submission_gate(node, {}, context)
    assert result.output["ready"] is False
    assert result.output["checks"]["has_accepted_finding"] is False
    assert "has_accepted_finding" in result.output["failed_checks"]


def _reset_flow_store():
    from semantica.explorer import flow_store

    flow_store._STORE = None
    return flow_store.get_flow_store()


def test_list_flows_does_not_seed():
    store = _reset_flow_store()
    from semantica.explorer.routes.flow import list_flows

    payload = list_flows()
    assert payload["flows"] == []
    assert store.list_flows() == []


def test_upsert_rejects_cycle_with_400():
    from fastapi import HTTPException

    from semantica.explorer.routes.flow import FlowUpsertRequest, upsert_flow

    _reset_flow_store()
    body = FlowUpsertRequest(
        flow={
            "id": "cyclic",
            "name": "cyclic",
            "nodes": [
                {"id": "a", "type": "trigger", "label": "A"},
                {"id": "b", "type": "merge", "label": "B"},
            ],
            "edges": [
                {"id": "e1", "source": "a", "target": "b"},
                {"id": "e2", "source": "b", "target": "a"},
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        upsert_flow(body)
    assert exc.value.status_code == 400
    assert "cycle" in str(exc.value.detail).lower()


def test_execute_does_not_write_run_status_onto_saved_flow():
    from semantica.explorer.routes.flow import FlowExecuteRequest, execute_flow

    store = _reset_flow_store()
    flow = build_bug_bounty_hunting_flow()
    store.upsert_flow(flow)
    before = {n.id: (n.status.value, n.result) for n in store.get_flow(flow.id).nodes}
    run = execute_flow(flow.id, FlowExecuteRequest(context={}, dry_run=False))
    assert run.get("id")
    after = {n.id: (n.status.value, n.result) for n in store.get_flow(flow.id).nodes}
    assert after == before
    assert store.get_run(run["id"]) is not None


def test_execute_dry_run_does_not_persist_run():
    from semantica.explorer.routes.flow import FlowExecuteRequest, execute_flow

    store = _reset_flow_store()
    flow = build_bug_bounty_hunting_flow()
    store.upsert_flow(flow)
    run = execute_flow(flow.id, FlowExecuteRequest(context={}, dry_run=True))
    assert run.get("id")
    assert store.get_run(run["id"]) is None
