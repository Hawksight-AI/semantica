"""
Pre-built n8n-style flow templates.

Includes the canonical bug bounty hunting flow for authorized research
case management with graph engineering.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import FlowEdge, FlowGraph, FlowNode


def _node(
    nid: str,
    ntype: str,
    label: str,
    x: float,
    y: float,
    config: Optional[Dict[str, Any]] = None,
    category: str = "bug_bounty",
    description: str = "",
) -> FlowNode:
    return FlowNode(
        id=nid,
        type=ntype,
        label=label,
        config=dict(config or {}),
        position={"x": x, "y": y},
        category=category,
        description=description,
    )


def _edge(source: str, target: str, label: str = "") -> FlowEdge:
    return FlowEdge(
        id=f"e_{source}_{target}",
        source=source,
        target=target,
        label=label,
    )


def build_bug_bounty_hunting_flow(
    program_name: str = "example-program",
    in_scope: Optional[List[str]] = None,
    out_of_scope: Optional[List[str]] = None,
    assets: Optional[List[Any]] = None,
    target: str = "app.example.com",
    finding_title: str = "Sample finding (replace with authorized research notes)",
    finding_severity: str = "medium",
    finding_description: str = (
        "Replace with a clear impact statement and reproduction notes collected "
        "under program authorization. Do not embed exploit payloads."
    ),
    evidence_text: str = (
        "Authorized evidence notes / screenshots metadata go here. "
        "Keep PII out of the graph when possible."
    ),
) -> FlowGraph:
    """
    Build the default bug bounty hunting flow (n8n-style DAG).

    Stages:
      Trigger → Program Scope → Scope Check → Asset Inventory → Evidence Ingest
      → Surface Map → Finding Record → Duplicate Check → Severity Triage
      → Report Compose → Submission Gate → Graph Export
    """
    in_scope = list(in_scope or ["*.example.com", "example.com"])
    out_of_scope = list(out_of_scope or ["blog.example.com", "*.third-party.example"])
    assets = list(
        assets
        or [
            {"host": "app.example.com", "kind": "web", "tags": ["primary"]},
            {"host": "api.example.com", "kind": "api", "tags": ["backend"]},
            {"host": "auth.example.com", "kind": "identity", "tags": ["auth"]},
        ]
    )

    nodes = [
        _node(
            "n_trigger",
            "trigger",
            "Start Hunt",
            0,
            180,
            {"payload": {"program_name": program_name, "target": target}},
            category="core",
            description="Kick off an authorized bug bounty case",
        ),
        _node(
            "n_scope",
            "program_scope",
            "Program Scope",
            220,
            80,
            {
                "program_name": program_name,
                "in_scope": in_scope,
                "out_of_scope": out_of_scope,
                "rules": [
                    "Only test assets listed as in-scope",
                    "No DoS, no social engineering, no data destruction",
                    "Report via the program channel with clear impact",
                ],
            },
            description="Load program policy and scope boundaries",
        ),
        _node(
            "n_scope_check",
            "scope_check",
            "Scope Gate",
            440,
            80,
            {"target": target, "block_out_of_scope": True},
            description="Fail-closed authorization check for the active target",
        ),
        _node(
            "n_assets",
            "asset_inventory",
            "Asset Inventory",
            660,
            80,
            {"assets": assets},
            description="Register declared in-scope assets into the case graph",
        ),
        _node(
            "n_evidence",
            "evidence_ingest",
            "Evidence Ingest",
            880,
            80,
            {
                "evidence": [
                    {
                        "title": "Research notes",
                        "text": evidence_text,
                        "source": "researcher",
                    }
                ]
            },
            description="Attach authorized evidence to the case graph",
        ),
        _node(
            "n_surface",
            "surface_map",
            "Surface Map",
            1100,
            80,
            {
                "relations": [
                    {
                        "source": "asset:app.example.com",
                        "target": "asset:api.example.com",
                        "type": "CALLS",
                    },
                    {
                        "source": "asset:app.example.com",
                        "target": "asset:auth.example.com",
                        "type": "AUTHENTICATES_VIA",
                    },
                ]
            },
            description="Graph-engineer relationships across declared assets",
        ),
        _node(
            "n_finding",
            "finding_record",
            "Finding Record",
            1320,
            180,
            {
                "title": finding_title,
                "severity": finding_severity,
                "description": finding_description,
                "asset": target,
                "cwe": "CWE-284",
                "confidence": 0.75,
            },
            description="Record a finding as a decision-linked graph object",
        ),
        _node(
            "n_dup",
            "duplicate_check",
            "Duplicate Check",
            1540,
            80,
            {"threshold": 0.85},
            description="Detect likely duplicate findings in the case graph",
        ),
        _node(
            "n_triage",
            "severity_triage",
            "Severity Triage",
            1760,
            80,
            {"min_severity": "low"},
            description="Apply severity policy and triage decisions",
        ),
        _node(
            "n_report",
            "report_compose",
            "Report Compose",
            1980,
            180,
            {"title": f"{program_name} — draft submission"},
            description="Compose a structured report from graph evidence",
        ),
        _node(
            "n_submit",
            "submission_gate",
            "Submission Gate",
            2200,
            180,
            {"block_if_not_ready": True},
            description="Final readiness checklist before submission",
        ),
        _node(
            "n_export",
            "graph_export",
            "Export Case Graph",
            2420,
            180,
            {"format": "semantica_case_graph"},
            category="graph",
            description="Export the full case knowledge graph",
        ),
    ]

    edges = [
        _edge("n_trigger", "n_scope"),
        _edge("n_scope", "n_scope_check", "scope loaded"),
        _edge("n_scope_check", "n_assets", "in scope"),
        _edge("n_assets", "n_evidence"),
        _edge("n_evidence", "n_surface"),
        _edge("n_surface", "n_finding"),
        _edge("n_finding", "n_dup"),
        _edge("n_dup", "n_triage"),
        _edge("n_triage", "n_report"),
        _edge("n_report", "n_submit"),
        _edge("n_submit", "n_export", "ready"),
    ]

    return FlowGraph(
        id=f"flow_bug_bounty_{uuid4().hex[:8]}",
        name="Bug Bounty Hunting",
        description=(
            "n8n-style graph workflow for authorized bug bounty case management: "
            "scope gates, asset inventory, evidence provenance, surface mapping, "
            "finding triage, report composition, and case-graph export."
        ),
        nodes=nodes,
        edges=edges,
        metadata={
            "template": "bug_bounty_hunting",
            "domain": "security_research",
            "authorized_only": True,
            "style": "n8n_graph",
        },
        version="1.0.0",
    )


class FlowTemplateManager:
    """Registry of named flow templates."""

    def __init__(self) -> None:
        self._builders = {
            "bug_bounty_hunting": build_bug_bounty_hunting_flow,
        }

    def list_templates(self) -> List[str]:
        return sorted(self._builders.keys())

    def create(
        self,
        template_name: str,
        **kwargs: Any,
    ) -> FlowGraph:
        if template_name not in self._builders:
            raise KeyError(f"Unknown flow template: {template_name}")
        return self._builders[template_name](**kwargs)

    def get_template_graph(self, template_name: str, **kwargs: Any) -> Dict[str, Any]:
        return self.create(template_name, **kwargs).to_dict()

    def describe(self, template_name: str) -> Dict[str, Any]:
        graph = self.create(template_name)
        return {
            "name": template_name,
            "title": graph.name,
            "description": graph.description,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "metadata": deepcopy(graph.metadata),
            "node_types": sorted({n.type for n in graph.nodes}),
        }
