"""
Built-in flow node handlers.

Bug-bounty nodes focus on authorized case management: scope gates, evidence
graphs, triage decisions, and report composition. They do not scan, exploit,
or generate attack payloads.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from .models import FlowNode, NodeExecutionResult
from .registry import NodeRegistry, NodeTypeSpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_host(value: str) -> str:
    value = value.strip().lower()
    if "://" in value:
        parsed = urlparse(value)
        host = parsed.hostname or value
    else:
        host = value.split("/")[0]
    if host.startswith("*."):
        return host
    return host.rstrip(".")


def _host_in_scope(host: str, allow: List[str], deny: List[str]) -> bool:
    host = _normalize_host(host)
    for pattern in deny:
        pat = _normalize_host(pattern)
        if host == pat or (pat.startswith("*.") and (host == pat[2:] or host.endswith("." + pat[2:]))):
            return False
        if host == pat or host.endswith("." + pat):
            return False
    for pattern in allow:
        pat = _normalize_host(pattern)
        if pat.startswith("*."):
            base = pat[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == pat or host.endswith("." + pat):
            return True
    return False


def _append_graph(context: Dict[str, Any], nodes: List[Dict], edges: List[Dict]) -> None:
    context.setdefault("graph_nodes", []).extend(nodes)
    context.setdefault("graph_edges", []).extend(edges)


# ── Generic nodes ───────────────────────────────────────────────────────────


def handle_trigger(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    payload = dict(node.config.get("payload") or {})
    payload.update(bag.get("inputs") or {})
    context.update({k: v for k, v in payload.items() if k not in ("dry_run",)})
    return NodeExecutionResult(
        output={"triggered": True, "payload": payload, "at": _now()},
        messages=["Flow triggered"],
    )


def handle_merge(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    merged: Dict[str, Any] = {}
    for _pred, out in (bag.get("upstream") or {}).items():
        if isinstance(out, dict):
            merged.update(out)
    return NodeExecutionResult(output=merged, messages=["Merged upstream outputs"])


def handle_decision_gate(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Pass/fail gate based on a boolean field in upstream output."""
    field = node.config.get("field", "allowed")
    inputs = bag.get("inputs") or {}
    allowed = bool(inputs.get(field, False))
    if not allowed and node.config.get("fail_closed", True):
        return NodeExecutionResult(
            output={"allowed": False, "field": field},
            messages=[f"Gate closed: {field} is false"],
            skip_downstream=True,
        )
    return NodeExecutionResult(
        output={"allowed": allowed, "field": field},
        messages=[f"Gate open: {field}={allowed}"],
    )


# ── Bug bounty / security research case-management nodes ───────────────────


def handle_program_scope(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Load program scope (in-scope / out-of-scope) into the run context."""
    program = node.config.get("program_name") or context.get("program_name") or "unnamed-program"
    in_scope = list(node.config.get("in_scope") or context.get("in_scope") or [])
    out_of_scope = list(node.config.get("out_of_scope") or context.get("out_of_scope") or [])
    rules = list(node.config.get("rules") or [])
    max_severity = node.config.get("max_severity", "critical")

    if not in_scope:
        raise ValueError("program_scope requires at least one in_scope asset pattern")

    scope = {
        "program_name": program,
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "rules": rules,
        "max_severity": max_severity,
        "loaded_at": _now(),
    }
    context["scope"] = scope
    context["program_name"] = program

    _append_graph(
        context,
        nodes=[
            {
                "id": f"program:{program}",
                "type": "BugBountyProgram",
                "label": program,
                "properties": scope,
            }
        ],
        edges=[],
    )

    return NodeExecutionResult(
        output={"scope": scope, "program_name": program},
        artifacts={"scope": scope},
        messages=[f"Loaded scope for {program}: {len(in_scope)} in-scope pattern(s)"],
    )


def handle_scope_check(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Authorize a target against program scope before any further work."""
    scope = context.get("scope") or {}
    allow = list(scope.get("in_scope") or node.config.get("in_scope") or [])
    deny = list(scope.get("out_of_scope") or node.config.get("out_of_scope") or [])
    target = (
        node.config.get("target")
        or (bag.get("inputs") or {}).get("target")
        or context.get("target")
    )
    if not target:
        raise ValueError("scope_check requires a target host or URL")

    allowed = _host_in_scope(str(target), allow, deny)
    result = {
        "target": target,
        "normalized": _normalize_host(str(target)),
        "in_scope": allowed,
        "allowed": allowed,
        "checked_at": _now(),
    }
    context["last_scope_check"] = result
    if not allowed:
        context.setdefault("scope_violations", []).append(result)

    _append_graph(
        context,
        nodes=[
            {
                "id": f"target:{result['normalized']}",
                "type": "Target",
                "label": result["normalized"],
                "properties": result,
            }
        ],
        edges=[
            {
                "id": f"e:scope:{result['normalized']}",
                "source": f"program:{context.get('program_name', 'unknown')}",
                "target": f"target:{result['normalized']}",
                "type": "IN_SCOPE" if allowed else "OUT_OF_SCOPE",
            }
        ]
        if context.get("program_name")
        else [],
    )

    messages = [
        f"Target {target} is {'IN' if allowed else 'OUT OF'} scope",
    ]
    skip = (not allowed) and bool(node.config.get("block_out_of_scope", True))
    return NodeExecutionResult(output=result, messages=messages, skip_downstream=skip)


def handle_asset_inventory(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Register declared in-scope assets as graph nodes (no active scanning)."""
    assets = list(node.config.get("assets") or context.get("assets") or [])
    inputs = bag.get("inputs") or {}
    if inputs.get("target") and not assets:
        assets = [{"host": inputs["target"], "kind": "host"}]

    scope = context.get("scope") or {}
    allow = list(scope.get("in_scope") or [])
    deny = list(scope.get("out_of_scope") or [])

    registered = []
    rejected = []
    nodes = []
    edges = []
    for raw in assets:
        if isinstance(raw, str):
            asset = {"host": raw, "kind": "host"}
        else:
            asset = dict(raw)
        host = asset.get("host") or asset.get("url") or asset.get("name")
        if not host:
            continue
        if allow and not _host_in_scope(str(host), allow, deny):
            rejected.append({"host": host, "reason": "out_of_scope"})
            continue
        asset_id = f"asset:{_normalize_host(str(host))}"
        record = {
            "id": asset_id,
            "host": _normalize_host(str(host)),
            "kind": asset.get("kind", "host"),
            "tags": asset.get("tags", []),
            "notes": asset.get("notes", ""),
            "registered_at": _now(),
        }
        registered.append(record)
        nodes.append(
            {
                "id": asset_id,
                "type": "Asset",
                "label": record["host"],
                "properties": record,
            }
        )
        if context.get("program_name"):
            edges.append(
                {
                    "id": f"e:owns:{asset_id}",
                    "source": f"program:{context['program_name']}",
                    "target": asset_id,
                    "type": "OWNS",
                }
            )

    context["assets"] = registered
    _append_graph(context, nodes, edges)
    return NodeExecutionResult(
        output={"assets": registered, "rejected": rejected, "count": len(registered)},
        messages=[f"Registered {len(registered)} asset(s); rejected {len(rejected)}"],
    )


def handle_evidence_ingest(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Ingest authorized evidence notes/docs into the case graph."""
    items = list(node.config.get("evidence") or context.get("evidence") or [])
    if not items and node.config.get("text"):
        items = [{"title": node.config.get("title", "note"), "text": node.config["text"]}]

    ingested = []
    nodes = []
    edges = []
    for item in items:
        if isinstance(item, str):
            item = {"title": "evidence", "text": item}
        text = item.get("text") or item.get("body") or ""
        title = item.get("title") or "evidence"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        eid = item.get("id") or f"evidence:{digest}"
        record = {
            "id": eid,
            "title": title,
            "text": text,
            "source": item.get("source", "manual"),
            "collected_at": item.get("collected_at") or _now(),
            "hash": digest,
        }
        ingested.append(record)
        nodes.append({"id": eid, "type": "Evidence", "label": title, "properties": record})
        target = (bag.get("inputs") or {}).get("normalized") or (bag.get("inputs") or {}).get("target")
        if target:
            edges.append(
                {
                    "id": f"e:evid:{eid}",
                    "source": eid,
                    "target": f"asset:{_normalize_host(str(target))}",
                    "type": "SUPPORTS",
                }
            )

    context.setdefault("evidence", []).extend(ingested)
    _append_graph(context, nodes, edges)
    return NodeExecutionResult(
        output={"evidence": ingested, "count": len(ingested)},
        messages=[f"Ingested {len(ingested)} evidence item(s)"],
    )


def handle_surface_map(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """
    Build an attack-surface *graph* from declared assets and relationships.

    This is graph engineering only: it links declared components. It does not
    probe hosts or discover services.
    """
    assets = list(context.get("assets") or (bag.get("inputs") or {}).get("assets") or [])
    relations = list(node.config.get("relations") or context.get("relations") or [])

    # Auto-link assets that share a registrable parent domain when no relations given.
    if not relations and len(assets) > 1:
        for i, a in enumerate(assets):
            for b in assets[i + 1 :]:
                ha, hb = a.get("host", ""), b.get("host", "")
                if ha and hb and ("." in ha and ha.split(".", 1)[-1] == hb.split(".", 1)[-1]):
                    relations.append(
                        {
                            "source": a["id"],
                            "target": b["id"],
                            "type": "SAME_SITE_FAMILY",
                        }
                    )

    nodes = [
        {
            "id": "surface:root",
            "type": "AttackSurface",
            "label": node.config.get("label", "Attack Surface Map"),
            "properties": {"built_at": _now(), "asset_count": len(assets)},
        }
    ]
    edges = []
    for asset in assets:
        edges.append(
            {
                "id": f"e:surface:{asset['id']}",
                "source": "surface:root",
                "target": asset["id"],
                "type": "INCLUDES",
            }
        )
    for rel in relations:
        edges.append(
            {
                "id": rel.get("id") or f"e:rel:{uuid4().hex[:8]}",
                "source": rel["source"],
                "target": rel["target"],
                "type": rel.get("type", "RELATED"),
            }
        )

    context["surface_map"] = {"assets": assets, "relations": relations}
    _append_graph(context, nodes, edges)
    return NodeExecutionResult(
        output={"surface_map": context["surface_map"], "relation_count": len(relations)},
        messages=[f"Mapped surface across {len(assets)} asset(s) with {len(relations)} relation(s)"],
    )


def handle_finding_record(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Record a researcher finding as a first-class graph + decision object."""
    title = node.config.get("title") or (bag.get("inputs") or {}).get("title")
    if not title:
        raise ValueError("finding_record requires a title")

    severity = (node.config.get("severity") or "medium").lower()
    description = node.config.get("description") or ""
    asset = node.config.get("asset") or (bag.get("inputs") or {}).get("normalized")
    cwe = node.config.get("cwe")
    evidence_ids = list(node.config.get("evidence_ids") or [])
    if not evidence_ids and context.get("evidence"):
        evidence_ids = [e["id"] for e in context["evidence"][-3:]]

    finding_id = node.config.get("id") or f"finding:{uuid4().hex[:10]}"
    finding = {
        "id": finding_id,
        "title": title,
        "severity": severity,
        "description": description,
        "asset": asset,
        "cwe": cwe,
        "evidence_ids": evidence_ids,
        "status": "draft",
        "recorded_at": _now(),
        "program": context.get("program_name"),
    }
    context.setdefault("findings", []).append(finding)

    decision = {
        "id": f"decision:{finding_id}",
        "category": "bug_bounty_finding",
        "scenario": title,
        "reasoning": description or f"Recorded {severity} finding",
        "outcome": "recorded",
        "confidence": float(node.config.get("confidence", 0.7)),
        "metadata": finding,
    }
    context.setdefault("decisions", []).append(decision)

    nodes = [
        {"id": finding_id, "type": "Finding", "label": title, "properties": finding},
        {
            "id": decision["id"],
            "type": "Decision",
            "label": f"Record: {title}",
            "properties": decision,
        },
    ]
    edges = [
        {
            "id": f"e:dec:{finding_id}",
            "source": decision["id"],
            "target": finding_id,
            "type": "RECORDS",
        }
    ]
    if asset:
        edges.append(
            {
                "id": f"e:aff:{finding_id}",
                "source": finding_id,
                "target": f"asset:{_normalize_host(str(asset))}",
                "type": "AFFECTS",
            }
        )
    for eid in evidence_ids:
        edges.append(
            {
                "id": f"e:fe:{finding_id}:{eid}",
                "source": eid,
                "target": finding_id,
                "type": "EVIDENCES",
            }
        )

    _append_graph(context, nodes, edges)
    return NodeExecutionResult(
        output={"finding": finding, "decision": decision},
        artifacts={"finding_id": finding_id},
        messages=[f"Recorded finding '{title}' ({severity})"],
    )


_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def handle_severity_triage(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Triage findings against program policy and duplicate signals."""
    findings = list(context.get("findings") or [])
    if not findings and (bag.get("inputs") or {}).get("finding"):
        findings = [(bag.get("inputs") or {})["finding"]]

    min_severity = (node.config.get("min_severity") or "low").lower()
    min_rank = _SEVERITY_RANK.get(min_severity, 1)
    triaged = []
    for finding in findings:
        sev = str(finding.get("severity", "info")).lower()
        rank = _SEVERITY_RANK.get(sev, 0)
        action = "accept" if rank >= min_rank else "downgrade_or_reject"
        if finding.get("status") == "duplicate":
            action = "duplicate"
        item = {**finding, "triage_action": action, "triaged_at": _now()}
        triaged.append(item)
        context.setdefault("decisions", []).append(
            {
                "id": f"decision:triage:{finding.get('id', uuid4().hex[:8])}",
                "category": "bug_bounty_triage",
                "scenario": finding.get("title"),
                "reasoning": f"Severity={sev}; policy min={min_severity}",
                "outcome": action,
                "confidence": 0.8,
            }
        )

    context["triaged_findings"] = triaged
    return NodeExecutionResult(
        output={"triaged": triaged, "count": len(triaged)},
        messages=[f"Triaged {len(triaged)} finding(s)"],
    )


def handle_duplicate_check(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Flag likely duplicate findings by normalized title similarity."""
    findings = list(context.get("findings") or [])
    threshold = float(node.config.get("threshold", 0.85))

    def _tokens(text: str) -> set:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    duplicates = []
    for i, a in enumerate(findings):
        ta = _tokens(a.get("title", ""))
        if not ta:
            continue
        for b in findings[i + 1 :]:
            tb = _tokens(b.get("title", ""))
            if not tb:
                continue
            score = len(ta & tb) / max(len(ta | tb), 1)
            if score >= threshold:
                b["status"] = "duplicate"
                duplicates.append(
                    {
                        "a": a.get("id"),
                        "b": b.get("id"),
                        "score": round(score, 3),
                    }
                )
                _append_graph(
                    context,
                    nodes=[],
                    edges=[
                        {
                            "id": f"e:dup:{a.get('id')}:{b.get('id')}",
                            "source": a.get("id"),
                            "target": b.get("id"),
                            "type": "LIKELY_DUPLICATE",
                            "properties": {"score": score},
                        }
                    ],
                )

    return NodeExecutionResult(
        output={"duplicates": duplicates, "count": len(duplicates)},
        messages=[f"Found {len(duplicates)} likely duplicate pair(s)"],
    )


def handle_report_compose(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Compose a structured vulnerability report from the case graph."""
    findings = list(context.get("triaged_findings") or context.get("findings") or [])
    accepted = [f for f in findings if f.get("triage_action", "accept") == "accept"]
    if node.config.get("include_all"):
        accepted = findings

    program = context.get("program_name", "program")
    sections = []
    for finding in accepted:
        sections.append(
            {
                "title": finding.get("title"),
                "severity": finding.get("severity"),
                "asset": finding.get("asset"),
                "cwe": finding.get("cwe"),
                "description": finding.get("description"),
                "evidence_ids": finding.get("evidence_ids", []),
                "status": finding.get("status", "draft"),
            }
        )

    report = {
        "id": f"report:{uuid4().hex[:10]}",
        "program": program,
        "title": node.config.get("title") or f"{program} — submission draft",
        "created_at": _now(),
        "findings": sections,
        "graph_summary": {
            "nodes": len(context.get("graph_nodes") or []),
            "edges": len(context.get("graph_edges") or []),
        },
        "disclaimer": (
            "Authorized bug bounty case package only. Scope was enforced by "
            "flow gates; no exploit payload is included."
        ),
    }
    markdown = [f"# {report['title']}", "", report["disclaimer"], ""]
    for section in sections:
        markdown.extend(
            [
                f"## {section['title']}",
                f"- Severity: `{section['severity']}`",
                f"- Asset: `{section.get('asset')}`",
                f"- CWE: `{section.get('cwe')}`",
                "",
                section.get("description") or "_No description_",
                "",
            ]
        )
    report["markdown"] = "\n".join(markdown)
    context["report"] = report

    _append_graph(
        context,
        nodes=[{"id": report["id"], "type": "Report", "label": report["title"], "properties": {"id": report["id"]}}],
        edges=[
            {
                "id": f"e:rep:{report['id']}:{f.get('id')}",
                "source": report["id"],
                "target": f.get("id"),
                "type": "INCLUDES_FINDING",
            }
            for f in accepted
            if f.get("id")
        ],
    )

    return NodeExecutionResult(
        output={"report": report},
        artifacts={"report_markdown": report["markdown"]},
        messages=[f"Composed report with {len(sections)} finding(s)"],
    )


def handle_submission_gate(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Final checklist before a researcher submits to the program."""
    report = context.get("report") or (bag.get("inputs") or {}).get("report")
    findings = list(context.get("triaged_findings") or context.get("findings") or [])
    scope = context.get("scope") or {}
    checks = {
        "has_scope": bool(scope.get("in_scope")),
        "has_report": bool(report),
        "has_accepted_finding": any(f.get("triage_action", "accept") == "accept" for f in findings)
        or bool(findings),
        "no_scope_violations": not bool(context.get("scope_violations")),
        "has_evidence": bool(context.get("evidence")),
    }
    required = list(node.config.get("required_checks") or checks.keys())
    failed = [k for k in required if not checks.get(k)]
    ready = len(failed) == 0
    result = {
        "ready": ready,
        "allowed": ready,
        "checks": checks,
        "failed_checks": failed,
        "checked_at": _now(),
    }
    context["submission_gate"] = result
    return NodeExecutionResult(
        output=result,
        messages=["Submission gate PASSED" if ready else f"Submission gate FAILED: {failed}"],
        skip_downstream=not ready and bool(node.config.get("block_if_not_ready", True)),
    )


def handle_graph_export(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Export the accumulated case knowledge graph from the run context."""
    nodes = list(context.get("graph_nodes") or [])
    edges = list(context.get("graph_edges") or [])
    # Deduplicate by id
    node_map = {n["id"]: n for n in nodes if n.get("id")}
    edge_map = {e["id"]: e for e in edges if e.get("id")}
    graph = {
        "nodes": list(node_map.values()),
        "edges": list(edge_map.values()),
        "exported_at": _now(),
        "format": node.config.get("format", "semantica_case_graph"),
    }
    context["exported_graph"] = graph
    return NodeExecutionResult(
        output={"graph": graph, "node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])},
        artifacts={"graph": graph},
        messages=[f"Exported case graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges"],
    )


def register_builtin_nodes(registry: NodeRegistry) -> None:
    """Register all built-in node types on the given registry."""
    specs = [
        NodeTypeSpec(
            type="trigger",
            label="Trigger",
            category="core",
            description="Start a flow with an optional payload",
            handler=handle_trigger,
            default_config={"payload": {}},
            color="#4cc38a",
        ),
        NodeTypeSpec(
            type="merge",
            label="Merge",
            category="core",
            description="Merge upstream outputs",
            handler=handle_merge,
            color="#8fa8c6",
        ),
        NodeTypeSpec(
            type="decision_gate",
            label="Decision Gate",
            category="core",
            description="Pass/fail gate on a boolean field",
            handler=handle_decision_gate,
            default_config={"field": "allowed", "fail_closed": True},
            color="#f2b66d",
        ),
        NodeTypeSpec(
            type="program_scope",
            label="Program Scope",
            category="bug_bounty",
            description="Load bug bounty program in-scope / out-of-scope rules",
            handler=handle_program_scope,
            default_config={"program_name": "", "in_scope": [], "out_of_scope": [], "rules": []},
            color="#4aa3ff",
        ),
        NodeTypeSpec(
            type="scope_check",
            label="Scope Check",
            category="bug_bounty",
            description="Authorize a target against program scope (fail-closed)",
            handler=handle_scope_check,
            default_config={"target": "", "block_out_of_scope": True},
            color="#ff7b72",
        ),
        NodeTypeSpec(
            type="asset_inventory",
            label="Asset Inventory",
            category="bug_bounty",
            description="Register declared in-scope assets as graph nodes",
            handler=handle_asset_inventory,
            default_config={"assets": []},
            color="#58a6ff",
        ),
        NodeTypeSpec(
            type="evidence_ingest",
            label="Evidence Ingest",
            category="bug_bounty",
            description="Ingest authorized evidence notes into the case graph",
            handler=handle_evidence_ingest,
            default_config={"evidence": []},
            color="#c084fc",
        ),
        NodeTypeSpec(
            type="surface_map",
            label="Surface Map",
            category="bug_bounty",
            description="Graph-engineer an attack-surface map from declared assets",
            handler=handle_surface_map,
            default_config={"relations": []},
            color="#7fd0ff",
        ),
        NodeTypeSpec(
            type="finding_record",
            label="Finding Record",
            category="bug_bounty",
            description="Record a finding with provenance and decision linkage",
            handler=handle_finding_record,
            default_config={"title": "", "severity": "medium", "description": ""},
            color="#f2b66d",
        ),
        NodeTypeSpec(
            type="duplicate_check",
            label="Duplicate Check",
            category="bug_bounty",
            description="Flag likely duplicate findings via title similarity",
            handler=handle_duplicate_check,
            default_config={"threshold": 0.85},
            color="#8fa8c6",
        ),
        NodeTypeSpec(
            type="severity_triage",
            label="Severity Triage",
            category="bug_bounty",
            description="Triage findings against severity policy",
            handler=handle_severity_triage,
            default_config={"min_severity": "low"},
            color="#f2b66d",
        ),
        NodeTypeSpec(
            type="report_compose",
            label="Report Compose",
            category="bug_bounty",
            description="Compose a structured submission draft from the case graph",
            handler=handle_report_compose,
            default_config={},
            color="#4cc38a",
        ),
        NodeTypeSpec(
            type="submission_gate",
            label="Submission Gate",
            category="bug_bounty",
            description="Final readiness checklist before program submission",
            handler=handle_submission_gate,
            default_config={"block_if_not_ready": True},
            color="#ff7b72",
        ),
        NodeTypeSpec(
            type="graph_export",
            label="Graph Export",
            category="graph",
            description="Export the accumulated case knowledge graph",
            handler=handle_graph_export,
            default_config={"format": "semantica_case_graph"},
            color="#56d364",
        ),
    ]
    for spec in specs:
        registry.register(spec)
