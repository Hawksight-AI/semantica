"""Tests for n8n-style flow graph engineering and bug bounty hunting template."""

from __future__ import annotations

import pytest

from semantica.flow import (
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
    assert "bug_bounty" in registry.categories()


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
