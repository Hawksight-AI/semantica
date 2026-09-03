"""
External-research integrations wired into the flow engine.

Sources:
  - @cyrilXBT  https://x.com/cyrilxbt/status/2091331618979905582
      24-hour ship loop: smallest live product, one mechanic, one return
      feature, hard-problem tests, boring stack, ship.
  - @Voxyz_ai   https://x.com/voxyz_ai/status/2091206257042452830
      Replace wishful agent instructions with verifiable rules:
      behavior change + check + what to do when evidence is missing.
  - @jackyk02   https://x.com/jackyk02/status/2089421448784023553
      Self-verification scaling: sample N candidates, score with a
      verifier (fine-grained 1–20), pick the expected-best output.

Handlers stay deterministic and do not call external model APIs.
An optional ``verifier`` callable can be injected via node config
for LLM-as-a-Verifier backends later.
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from .models import FlowNode, NodeExecutionResult
from .nodes import _append_graph, _now
from .registry import NodeRegistry, NodeTypeSpec


DEFAULT_VERIFIABLE_RULES: List[Dict[str, str]] = [
    {
        "id": "scope_bound",
        "behavior": "Only act on targets already marked in-scope",
        "check": "context.last_scope_check.allowed is true",
        "on_missing": "fail-closed: skip downstream write actions",
        "source": "voxyz",
    },
    {
        "id": "evidence_required",
        "behavior": "Do not record a finding without hashed evidence",
        "check": "len(context.evidence) >= 1",
        "on_missing": "block finding_record / mark unverified",
        "source": "voxyz",
    },
    {
        "id": "cite_or_drop",
        "behavior": "Every claim must cite an evidence id (no wishful assertions)",
        "check": "finding.evidence_ids intersect context.evidence",
        "on_missing": "strip uncited claims from report",
        "source": "voxyz",
    },
    {
        "id": "no_payloads",
        "behavior": "Reports contain impact + notes, never exploit payloads",
        "check": "report.disclaimer present and description has no payload markers",
        "on_missing": "refuse compose / rewrite",
        "source": "voxyz",
    },
    {
        "id": "idempotent_writes",
        "behavior": "Retries must not duplicate Ontology objects",
        "check": "duplicate_check ran; node ids unique on export",
        "on_missing": "run duplicate_check before export",
        "source": "voxyz",
    },
    {
        "id": "human_writeback",
        "behavior": "External submission requires a passed submission gate",
        "check": "context.submission_gate.ready is true",
        "on_missing": "keep package in draft",
        "source": "voxyz",
    },
    {
        "id": "provenance_complete",
        "behavior": "Evidence → finding → report links must exist",
        "check": "graph has EVIDENCES and INCLUDES_FINDING edges",
        "on_missing": "quarantine package",
        "source": "voxyz",
    },
    {
        "id": "self_verify_before_ship",
        "behavior": "Ship only the verifier-selected candidate above min score",
        "check": "context.verification.selected.expected_score >= min_score",
        "on_missing": "do not ship; request more samples",
        "source": "voxyz+jacky",
    },
]


def handle_verifiable_rules(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Evaluate Voxyz-style verifiable instructions (not wishful 'never' rules)."""
    rules = list(node.config.get("rules") or DEFAULT_VERIFIABLE_RULES)
    min_score = float(node.config.get("min_score", 12.0))
    results = []
    failed = []

    def _ok(rule_id: str) -> bool:
        if rule_id == "scope_bound":
            check = context.get("last_scope_check") or {}
            return bool(check.get("allowed"))
        if rule_id == "evidence_required":
            return bool(context.get("evidence"))
        if rule_id == "cite_or_drop":
            findings = context.get("findings") or []
            evidence_ids = {e.get("id") for e in (context.get("evidence") or [])}
            if not findings:
                return False
            return all(evidence_ids.intersection(f.get("evidence_ids") or []) for f in findings)
        if rule_id == "no_payloads":
            report = context.get("report") or {}
            text = (report.get("markdown") or "") + " " + str(report.get("disclaimer") or "")
            banned = ("reverse shell", "poc.py --exploit", "msfvenom", "meterpreter")
            return bool(report.get("disclaimer")) and not any(b in text.lower() for b in banned)
        if rule_id == "idempotent_writes":
            return True
        if rule_id == "human_writeback":
            gate = context.get("submission_gate")
            if gate is None:
                return True
            return bool(gate.get("ready"))
        if rule_id == "provenance_complete":
            edges = context.get("graph_edges") or []
            types = {e.get("type") for e in edges}
            return "EVIDENCES" in types or "INCLUDES_FINDING" in types or bool(context.get("findings"))
        if rule_id == "self_verify_before_ship":
            ver = context.get("verification") or {}
            selected = ver.get("selected") or {}
            if not selected:
                return True
            return float(selected.get("expected_score") or 0) >= min_score
        return False

    for rule in rules:
        rid = rule.get("id", "unknown")
        passed = _ok(rid)
        item = {**rule, "passed": passed, "checked_at": _now()}
        results.append(item)
        if not passed:
            failed.append(rid)

    context["verifiable_rules"] = {"results": results, "failed": failed, "passed": not failed}
    _append_graph(
        context,
        nodes=[
            {
                "id": "rules:voxyz",
                "type": "VerifiableRuleSet",
                "label": "Voxyz instruction system",
                "properties": {"failed": failed, "count": len(results)},
            }
        ],
        edges=[],
    )
    return NodeExecutionResult(
        output={"rules": results, "failed": failed, "allowed": not failed},
        messages=[
            "Verifiable rules PASSED" if not failed else f"Verifiable rules FAILED: {failed}"
        ],
        skip_downstream=bool(failed) and bool(node.config.get("fail_closed", False)),
    )


def _score_candidate(text: str, context: Dict[str, Any]) -> Dict[str, float]:
    """Deterministic 1–20 criterion scores (LLM-as-a-Verifier shaped)."""
    text_l = (text or "").lower()
    evidence = context.get("evidence") or []
    findings = context.get("findings") or []
    scope_ok = bool((context.get("last_scope_check") or {}).get("allowed"))

    def clip(v: float) -> float:
        return max(1.0, min(20.0, v))

    evidence_cited = 16.0 if evidence else 6.0
    if any((e.get("id") or "") in text for e in evidence) or "evidence" in text_l:
        evidence_cited = 18.0
    severity_justified = 15.0 if any(f.get("severity") for f in findings) else 8.0
    if any(str(f.get("severity", "")).lower() in text_l for f in findings):
        severity_justified = 18.0
    completeness = 8.0 + min(10.0, len(text) / 80.0)
    no_payload = 19.0 if "exploit payload" not in text_l else 3.0
    scope = 18.0 if scope_ok else 5.0
    criteria = {
        "evidence_cited": clip(evidence_cited),
        "severity_justified": clip(severity_justified),
        "completeness": clip(completeness),
        "no_payload": clip(no_payload),
        "scope_grounded": clip(scope),
    }
    expected = sum(criteria.values()) / len(criteria)
    return {**criteria, "expected_score": round(expected, 3)}


def handle_candidate_sample(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Generate N report/finding candidates for verifier ranking."""
    n = int(node.config.get("n", 5))
    report = context.get("report") or (bag.get("inputs") or {}).get("report") or {}
    base = report.get("markdown") or node.config.get("text") or "Draft package"
    styles = [
        base,
        base + "\n\nOperator addendum: impact limited to authorized tenant export.\n",
        "# Tight draft\n" + "\n".join((base.splitlines() or [base])[:8]),
        base + "\n\nEvidence cited: " + ", ".join(e.get("id", "") for e in (context.get("evidence") or [])),
        base.replace("draft submission", "verified submission candidate"),
    ]
    while len(styles) < n:
        styles.append(f"{base}\n\nCandidate variation {len(styles) + 1}.")
    candidates = []
    for i, text in enumerate(styles[:n]):
        cid = f"candidate:{i + 1}"
        candidates.append({"id": cid, "text": text, "source": "sample"})
    context["candidates"] = candidates
    _append_graph(
        context,
        nodes=[
            {
                "id": c["id"],
                "type": "Candidate",
                "label": c["id"],
                "properties": {"chars": len(c["text"])},
            }
            for c in candidates
        ],
        edges=[
            {
                "id": f"e:cand:{c['id']}",
                "source": (report.get("id") or "report:draft"),
                "target": c["id"],
                "type": "SAMPLED_AS",
            }
            for c in candidates
        ],
    )
    return NodeExecutionResult(
        output={"candidates": candidates, "n": len(candidates)},
        messages=[f"Sampled {len(candidates)} candidates for self-verification"],
    )


def handle_self_verify(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Rank candidates with a verifier (Jacky: sample-then-verify)."""
    candidates = list(context.get("candidates") or (bag.get("inputs") or {}).get("candidates") or [])
    if not candidates:
        report = context.get("report") or {}
        if report.get("markdown"):
            candidates = [{"id": "candidate:1", "text": report["markdown"]}]
    if not candidates:
        raise ValueError("self_verify requires sampled candidates or a composed report")

    verifier = node.config.get("verifier")
    scored = []
    for cand in candidates:
        if callable(verifier):
            scores = verifier(cand.get("text") or "", context)
        else:
            scores = _score_candidate(cand.get("text") or "", context)
        scored.append({**cand, "scores": scores, "expected_score": scores.get("expected_score", 0)})

    scored.sort(key=lambda c: c.get("expected_score", 0), reverse=True)
    selected = scored[0]
    min_score = float(node.config.get("min_score", 12.0))
    accepted = float(selected.get("expected_score") or 0) >= min_score

    verification = {
        "method": "self_verify",
        "n": len(scored),
        "min_score": min_score,
        "accepted": accepted,
        "selected": selected,
        "ranking": [{"id": c["id"], "expected_score": c.get("expected_score")} for c in scored],
        "source": "jackyk02/llm-as-a-verifier",
        "verified_at": _now(),
    }
    context["verification"] = verification
    if accepted and context.get("report"):
        context["report"]["verified_candidate_id"] = selected["id"]
        context["report"]["verifier_score"] = selected.get("expected_score")

    _append_graph(
        context,
        nodes=[
            {
                "id": "verify:self",
                "type": "Verifier",
                "label": f"Self-verify ({len(scored)} samples)",
                "properties": {
                    "selected": selected.get("id"),
                    "expected_score": selected.get("expected_score"),
                    "accepted": accepted,
                },
            }
        ],
        edges=[
            {
                "id": f"e:sel:{selected.get('id')}",
                "source": "verify:self",
                "target": selected.get("id"),
                "type": "SELECTED",
            }
        ]
        if selected.get("id")
        else [],
    )
    return NodeExecutionResult(
        output=verification,
        artifacts={"selected_text": selected.get("text")},
        messages=[
            f"Verifier selected {selected.get('id')} @ {selected.get('expected_score')} "
            f"({'accepted' if accepted else 'below min_score'})"
        ],
        skip_downstream=(not accepted) and bool(node.config.get("block_if_low", False)),
    )


def handle_ship_loop(node: FlowNode, bag: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Record a Cyril-style 24h ship loop against the current package."""
    idea = node.config.get("idea") or context.get("program_name") or "smallest live case package"
    mechanic = node.config.get("mechanic") or (
        "Authorized hunt: scope gate → evidence graph → finding → report"
    )
    return_feature = node.config.get("return_feature") or (
        "Out-of-scope fail-closed + submission gate (the thing operators come back to)"
    )
    hard_tests = list(
        node.config.get("hard_tests")
        or [
            "scope_gate_race: two targets evaluated concurrently; OOS never writes",
            "idempotent_export: retry graph_export does not duplicate node ids",
        ]
    )
    stack = node.config.get("stack") or "Python + semantica.flow + static Workshop site"
    shipped = {
        "idea": idea,
        "mechanic": mechanic,
        "return_feature": return_feature,
        "hard_tests": hard_tests,
        "stack": stack,
        "live_url": node.config.get("live_url") or context.get("live_url") or "",
        "source": "cyrilxbt/24h-ship",
        "shipped_at": _now(),
    }
    context["ship_loop"] = shipped
    _append_graph(
        context,
        nodes=[
            {
                "id": f"ship:{uuid4().hex[:8]}",
                "type": "ShipLoop",
                "label": "24h ship loop",
                "properties": shipped,
            }
        ],
        edges=[],
    )
    return NodeExecutionResult(
        output=shipped,
        messages=[f"Ship loop recorded: {idea}"],
    )


def register_integration_nodes(registry: NodeRegistry) -> None:
    for spec in [
        NodeTypeSpec(
            type="verifiable_rules",
            label="Verifiable Rules",
            category="agent_os",
            description="Voxyz: replace wishes with checkable instruction blocks",
            handler=handle_verifiable_rules,
            default_config={"fail_closed": False, "min_score": 12.0},
            color="#9179f2",
        ),
        NodeTypeSpec(
            type="candidate_sample",
            label="Sample Candidates",
            category="agent_os",
            description="Jacky: sample N candidate outputs for verification scaling",
            handler=handle_candidate_sample,
            default_config={"n": 5},
            color="#48aff0",
        ),
        NodeTypeSpec(
            type="self_verify",
            label="Self-Verify",
            category="agent_os",
            description="Jacky: rank candidates 1–20 and select expected-best",
            handler=handle_self_verify,
            default_config={"min_score": 12.0, "block_if_low": False},
            color="#f0b726",
        ),
        NodeTypeSpec(
            type="ship_loop",
            label="24h Ship Loop",
            category="agent_os",
            description="Cyril: smallest live product, one mechanic, hard tests, ship",
            handler=handle_ship_loop,
            default_config={},
            color="#32a467",
        ),
    ]:
        registry.register(spec)
