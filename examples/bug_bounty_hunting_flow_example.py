#!/usr/bin/env python3
"""
Bug Bounty Hunting Flow — graph engineering example (n8n-style).

Runs the authorized bug bounty case-management DAG:
  scope → gate → assets → evidence → surface map → finding →
  duplicates → triage → report → submission gate → graph export

This is case/graph orchestration only. It does not scan or exploit targets.
"""

from __future__ import annotations

import json
import sys

from semantica.flow import FlowEngine, build_bug_bounty_hunting_flow


def main() -> int:
    flow = build_bug_bounty_hunting_flow(
        program_name="acme-public-bb",
        in_scope=["*.acme.example", "acme.example"],
        out_of_scope=["blog.acme.example", "status.acme.example"],
        target="app.acme.example",
        assets=[
            {"host": "app.acme.example", "kind": "web", "tags": ["primary"]},
            {"host": "api.acme.example", "kind": "api", "tags": ["backend"]},
            {"host": "auth.acme.example", "kind": "identity", "tags": ["auth"]},
        ],
        finding_title="Broken access control on project export (authorized notes)",
        finding_severity="high",
        finding_description=(
            "Under program authorization, export endpoint accepted another tenant's "
            "project id. Impact: cross-tenant data exposure. Replace with your notes."
        ),
        evidence_text=(
            "Request/response metadata captured during authorized testing. "
            "No credentials or PII stored in the graph."
        ),
    )

    # Adjust surface-map relations for the ACME hosts used above.
    for node in flow.nodes:
        if node.type == "surface_map":
            node.config["relations"] = [
                {
                    "source": "asset:app.acme.example",
                    "target": "asset:api.acme.example",
                    "type": "CALLS",
                },
                {
                    "source": "asset:app.acme.example",
                    "target": "asset:auth.acme.example",
                    "type": "AUTHENTICATES_VIA",
                },
            ]

    engine = FlowEngine()
    errors = engine.validate(flow)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    run = engine.execute(flow)
    print(f"Flow: {flow.name} ({flow.id})")
    print(f"Run status: {run.status.value}")
    print(f"Nodes executed: {len(run.node_status)}")
    for node_id, status in run.node_status.items():
        messages = run.node_results.get(node_id, {}).get("messages") or []
        msg = f" — {messages[0]}" if messages else ""
        print(f"  [{status}] {node_id}{msg}")

    report = run.context.get("report") or {}
    graph = run.context.get("exported_graph") or {}
    gate = run.context.get("submission_gate") or {}

    print("\n--- Submission gate ---")
    print(json.dumps(gate, indent=2))
    print("\n--- Case graph summary ---")
    print(
        json.dumps(
            {
                "nodes": len(graph.get("nodes") or []),
                "edges": len(graph.get("edges") or []),
            },
            indent=2,
        )
    )
    if report.get("markdown"):
        print("\n--- Report draft ---")
        print(report["markdown"])

    return 0 if run.status.value == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
