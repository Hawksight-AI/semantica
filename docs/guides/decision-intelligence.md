---
title: "Decision Intelligence"
description: "How Semantica records, stores, traces, and queries AI agent decisions as first-class knowledge graph objects — with causal chains, precedent search, policy enforcement, and full explainability."
icon: "scale-balanced"
---

`AgentContext.record_decision()` stores every AI decision as a node in the knowledge graph, linked by causal edges to the decisions that preceded it and the outcomes that followed. Use it to build an auditable reasoning trail — one that lets you reconstruct, six months later, exactly which classification caused which escalation, and which policy was checked before it was recorded.

<Info>
  Decision tracking requires both a `VectorStore` (for embedding-based precedent search) and a `ContextGraph` (for causal graph storage). Set `decision_tracking=True` on `AgentContext` — omitting either component raises `RuntimeError` at call time.
</Info>

## Recording the First Decision

The most common entry point is `AgentContext.record_decision()`. It writes a `Decision` node into the graph, generates embeddings for hybrid similarity search, and returns a UUID you use to link subsequent decisions causally.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

graph   = ContextGraph(advanced_analytics=True)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    decision_tracking=True,
)

# The system has just classified a new threat cluster.
# Record the classification decision before taking any action.
classification_id = context.record_decision(
    category       = "threat_classification",
    scenario       = "Unattributed C2 cluster using HAMMERTOSS-like Twitter dead-drop pattern",
    reasoning      = "Infrastructure overlaps known APT29 hosting ASN; TTP T1102 matches NOBELIUM playbook with 0.88 cosine similarity",
    outcome        = "classified_as_apt29_cluster",
    confidence     = 0.88,
    decision_maker = "cti_pipeline_v2",
    entities       = ["apt29", "hammertoss", "twitter_c2"],
)

print("Decision recorded:", classification_id)
# → "Decision recorded: dec_a3f2b1c4-..."
```

The `Decision` dataclass that backs this node has the following fields — these are what get stored and searched:

```python
from semantica.context import Decision
from datetime import datetime

# Constructing a Decision explicitly (alternative to record_decision)
d = Decision(
    decision_id    = "dec_001",           # UUID — auto-generated if omitted via record_decision
    category       = "threat_classification",
    scenario       = "Unattributed C2 cluster",
    reasoning      = "Infrastructure overlaps APT29 ASN",
    outcome        = "classified_as_apt29_cluster",
    confidence     = 0.88,               # float 0.0–1.0
    timestamp      = datetime.now(),
    decision_maker = "cti_pipeline_v2",
    # optional fields:
    valid_from     = "2025-07-01T00:00:00",   # ISO datetime
    valid_until    = "2025-09-30T23:59:59",   # ISO datetime
    metadata       = {"source_feed": "isac_partner_b"},
)
graph.add_decision(d)
```

## Searching Precedents Before Deciding

Before making a significant call, the system should search past decisions for similar scenarios. This is how you prevent the same cluster being classified differently across two agent runs — the second agent finds the first agent's decision and uses it as a prior.

```python
# Search before classifying a new unattributed cluster
precedents = context.find_precedents(
    "unattributed C2 cluster Twitter dead-drop infrastructure",
    limit=5,
)

for p in precedents:
    print("[{:.2f} confidence] {} → {}".format(p.confidence, p.category, p.outcome))
    print("  Reasoning: {}".format(p.reasoning[:80]))
    print("  Similarity: {:.3f}".format(p.metadata.get("similarity_score", 0)))
```

Hybrid search blends two signals: semantic similarity over the `scenario` and `reasoning` text (weight 0.7), and structural graph proximity via Node2Vec embeddings (weight 0.3). The result is a ranked list of `Decision` objects — the most similar past decisions float to the top regardless of how differently they were phrased.

## Building a Causal Chain

Decisions rarely exist in isolation. A classification decision causes an escalation decision, which causes a containment decision. Linking them with causal edges lets you traverse the chain in either direction — upstream to understand what caused an outcome, downstream to see what an early decision triggered.

```python
# The classification above caused an escalation
escalation_id = context.record_decision(
    category       = "escalation",
    scenario       = "APT29 cluster confirmed — active C2 beaconing to NATO contractor subnet",
    reasoning      = "Classification confidence 0.88 exceeds 0.80 escalation threshold; active C2 requires immediate SOC notification",
    outcome        = "escalated_to_soc_tier2",
    confidence     = 0.95,
    decision_maker = "escalation_engine",
)

# Link the two decisions: classification caused the escalation
graph.add_causal_relationship(classification_id, escalation_id, "CAUSED")

# The escalation influenced a patch prioritization decision
patch_id = context.record_decision(
    category       = "patch_priority",
    scenario       = "CVE-2024-3400 present in two NATO contractor VPN appliances",
    reasoning      = "Active exploitation by classified APT29 cluster elevates CVE-2024-3400 to P0 regardless of base CVSS",
    outcome        = "prioritized_cve_2024_3400_p0",
    confidence     = 0.97,
    decision_maker = "patch_engine",
)

graph.add_causal_relationship(escalation_id, patch_id, "INFLUENCED")
```

Now trace the chain from the patch decision back to its root cause:

```python
upstream = context.get_causal_chain(
    patch_id,
    direction = "upstream",
    max_depth = 5,
)

print("Causal chain upstream from patch prioritization:")
for d in upstream:
    depth = d.metadata.get("causal_distance", "?")
    print("  [depth {}] {} → {}  (confidence={:.2f})".format(
        depth, d.category, d.outcome, d.confidence
    ))
# [depth 1] escalation → escalated_to_soc_tier2  (confidence=0.95)
# [depth 2] threat_classification → classified_as_apt29_cluster  (confidence=0.88)
```

And trace downstream from the original classification to see everything it triggered:

```python
downstream = context.get_causal_chain(
    classification_id,
    direction = "downstream",
    max_depth = 5,
)
print("Downstream decisions triggered:", len(downstream))
for d in downstream:
    print("  → {} [{}]".format(d.outcome, d.category))
```

## Generating an Explainability Report

`trace_decision_explainability` gives you the full picture in one call: upstream causes, downstream effects, and total connection count. This is what you attach to a post-mortem or audit report.

```python
explanation = context.trace_decision_explainability(patch_id)

print("Decision:", patch_id)
print("Total graph connections :", explanation["total_connections"])
print("Upstream causes         :", len(explanation.get("upstream_decisions", [])))
print("Downstream effects      :", len(explanation.get("downstream_decisions", [])))
```

For deeper causal analysis with confidence decay and distance bands, use `trace_decision_causality` on the graph directly:

```python
chains = graph.trace_decision_causality(patch_id, max_depth=5)

for chain in chains:
    print("Chain: {} hops | band={} | decay={:.3f}".format(
        chain["hop_count"], chain["distance_band"], chain["confidence_decay"]
    ))
    print("  Interpretation:", chain["interpretation"])
    # e.g. "Decision chain spans 2 hops in the 'near' band with 84% confidence
    #        — causal attribution is reliable."
```

## Gating Decisions Against Policy

Before recording a high-stakes decision, check it against a versioned policy. The `PolicyEngine` stores `Policy` nodes in the graph and gates `Decision` objects against their rules.

```python
from semantica.context import PolicyEngine, Policy, Decision
from datetime import datetime

engine = PolicyEngine(graph_store=graph)

engine.add_policy(Policy(
    policy_id   = "cti_confidence_gate",
    name        = "CTI Minimum Confidence Policy",
    description = "All threat classifications must have confidence >= 0.80",
    rules       = {"min_confidence": 0.80, "requires_reasoning": True},
    category    = "threat_classification",
    version     = "1.0",
    created_at  = datetime.now(),
    updated_at  = datetime.now(),
))

d = Decision(
    decision_id    = "dec_low_conf",
    category       = "threat_classification",
    scenario       = "Possible APT29 activity — weak signals only",
    reasoning      = "Single IP overlap, no TTP match",
    outcome        = "classified_as_apt29_tentative",
    confidence     = 0.62,   # below the 0.80 threshold
    timestamp      = datetime.now(),
    decision_maker = "cti_pipeline_v2",
)

if engine.check_compliance(d, "cti_confidence_gate"):
    graph.add_decision(d)
    engine.record_policy_application(d.decision_id, "cti_confidence_gate", "1.0")
    print("Decision recorded — policy compliant.")
else:
    print("Decision blocked — confidence 0.62 below policy minimum 0.80.")
    # → "Decision blocked — confidence 0.62 below policy minimum 0.80."
```

When a high-urgency situation requires bypassing the policy gate, record the exception with the approver identity and justification:

```python
from semantica.context import DecisionRecorder

recorder = DecisionRecorder(graph_store=graph)

exception_id = recorder.record_exception(
    decision_id     = "dec_low_conf",
    policy_id       = "cti_confidence_gate",
    reason          = "Active exploitation in progress — cannot wait for higher-confidence attribution",
    approver        = "ciso_director",
    approval_method = "slack_dm",
    justification   = "Time-critical incident response; manual CISO sign-off obtained at 03:14 UTC",
)
print("Policy exception recorded:", exception_id)
```

For multi-level approval workflows, use `DecisionRecorder.record_approval_chain()` with a graph database backend (for example Neo4j/FalkorDB). The in-memory `ContextGraph` examples used in this guide do not support approval-chain persistence via `execute_query()`.



## Generating a Decision Audit Report

At the end of a shift or incident, `get_decision_insights` produces a statistical summary of every decision in the graph — useful for shift handover notes and compliance reporting.

```python
insights = graph.get_decision_insights()

print("Total decisions today :", insights["total_decisions"])
print("Confidence — mean={:.2f}  min={:.2f}  max={:.2f}".format(
    insights["confidence_stats"]["mean"],
    insights["confidence_stats"]["min"],
    insights["confidence_stats"]["max"],
))
print("\nDecisions by category:")
for cat, count in sorted(insights["categories"].items(), key=lambda x: -x[1]):
    print("  {:35s} {}".format(cat, count))
print("\nOutcomes:")
for outcome, count in sorted(insights["outcomes"].items(), key=lambda x: -x[1]):
    print("  {:35s} {}".format(outcome, count))
```

Sample output:

```text
Total decisions today : 47
Confidence — mean=0.87  min=0.62  max=0.99

Decisions by category:
  threat_classification                 18
  patch_priority                        12
  escalation                             9
  containment                            8

Outcomes:
  classified_as_apt29_cluster           11
  prioritized_p0_patch                  12
  escalated_to_soc_tier2                 9
  isolated_host                          8
```

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

A CTI pipeline classifies threat clusters, records each classification with confidence and reasoning, links classification decisions to escalation decisions causally, and generates a daily audit report for the threat intelligence lead.

```python
from semantica.context import AgentContext, ContextGraph, PolicyEngine, Policy
from semantica.vector_store import VectorStore
from datetime import datetime

graph   = ContextGraph(advanced_analytics=True)
engine  = PolicyEngine(graph_store=graph)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    decision_tracking=True,
)

engine.add_policy(Policy(
    policy_id   = "cti_gate",
    name        = "CTI Attribution Confidence Gate",
    description = "Attributions require confidence >= 0.80",
    rules       = {"min_confidence": 0.80},
    category    = "threat_classification",
    version     = "1.0",
    created_at  = datetime.now(),
    updated_at  = datetime.now(),
))

# Check precedents before classifying
precedents = context.find_precedents(
    "Twitter dead-drop C2 pattern overlapping APT29 infrastructure",
    limit=3,
)
for p in precedents:
    print("Prior: {} → {} ({:.0%})".format(p.scenario[:40], p.outcome, p.confidence))

# Record the classification
class_id = context.record_decision(
    category       = "threat_classification",
    scenario       = "New C2 cluster: Twitter dead-drop, AS200651 hosting, TTP T1102",
    reasoning      = "IP block overlaps APT29 cluster; T1102 matches HAMMERTOSS playbook",
    outcome        = "classified_apt29_march_cluster",
    confidence     = 0.88,
    decision_maker = "cti_pipeline_v2",
    entities       = ["apt29", "hammertoss"],
)

# Link to downstream escalation
esc_id = context.record_decision(
    category       = "escalation",
    scenario       = "APT29 cluster active — beaconing to NATO subnet 10.30.0.0/16",
    reasoning      = "Active C2 with high-confidence attribution requires immediate SOC notification",
    outcome        = "escalated_tier2_soc",
    confidence     = 0.97,
    decision_maker = "escalation_engine",
)
graph.add_causal_relationship(class_id, esc_id, "CAUSED")

# Post-shift audit report
insights = graph.get_decision_insights()
print("Decisions recorded:", insights["total_decisions"])
print("Mean confidence   :", round(insights["confidence_stats"]["mean"], 2))
```

</Tab>

<Tab title="Security — SOC/Incident">

During an incident, the SOC records containment decisions with causal links to the detection decisions that triggered them. Six hours later the post-mortem can replay the exact decision sequence from first alert to final containment.

```python
from semantica.context import AgentContext, ContextGraph, DecisionRecorder
from semantica.vector_store import VectorStore

graph    = ContextGraph()
recorder = DecisionRecorder(graph_store=graph)
context  = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    decision_tracking=True,
)

# T+0: Detection decision
detect_id = context.record_decision(
    category       = "detection",
    scenario       = "WKSTN-047: wmiprvse.exe spawned scheduled task — T1053.005",
    reasoning      = "Scheduled task creation by WMI provider host is high-fidelity lateral movement indicator",
    outcome        = "flagged_wkstn047_suspicious",
    confidence     = 0.93,
    decision_maker = "edr_engine",
)

# T+8min: Containment decision caused by detection
contain_id = context.record_decision(
    category       = "containment",
    scenario       = "WKSTN-047 confirmed compromised — lateral movement to DC01 via SMB",
    reasoning      = "PsExec artefact on DC01; isolate before domain-wide credential compromise",
    outcome        = "isolated_wkstn047",
    confidence     = 0.95,
    decision_maker = "analyst_chen",
)
graph.add_causal_relationship(detect_id, contain_id, "CAUSED")

# Post-mortem: trace the full chain
chain = context.get_causal_chain(contain_id, direction="upstream", max_depth=5)
print("Post-mortem — causal chain for isolation decision:")
for d in chain:
    print("  [depth {}] {} → {}  (confidence={:.2f}, maker={})".format(
        d.metadata.get("causal_distance", "?"),
        d.category, d.outcome, d.confidence, d.decision_maker,
    ))

# Full explainability for the containment decision
explanation = context.trace_decision_explainability(contain_id)
print("Upstream causes   :", len(explanation.get("upstream_decisions", [])))
print("Total connections :", explanation["total_connections"])
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

A clinical AI assistant records treatment modification decisions with guideline precedents, links them causally to the diagnostic decisions that preceded them, and generates a structured decision record for MDT review and regulatory audit.

```python
from semantica.context import AgentContext, ContextGraph, PolicyEngine, Policy
from semantica.context import Decision, DecisionRecorder
from semantica.vector_store import VectorStore
from datetime import datetime

graph   = ContextGraph()
engine  = PolicyEngine(graph_store=graph)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    decision_tracking=True,
)

engine.add_policy(Policy(
    policy_id   = "clinical_confidence_gate",
    name        = "Clinical Decision Confidence Gate",
    description = "Treatment decisions require confidence >= 0.90",
    rules       = {"min_confidence": 0.90},
    category    = "treatment_modification",
    version     = "1.0",
    created_at  = datetime.now(),
    updated_at  = datetime.now(),
))

# Diagnostic decision precedes treatment decision
diag_id = context.record_decision(
    category       = "diagnosis_assessment",
    scenario       = "Patient eGFR 28 mL/min/1.73m2, CKD Stage 4, current metformin 1000mg BD",
    reasoning      = "eGFR 28 confirms CKD Stage 4; below 30 threshold for metformin contraindication",
    outcome        = "confirmed_ckd_stage4_metformin_contraindicated",
    confidence     = 0.99,
    decision_maker = "clinical_ai_v3",
)

# Treatment modification caused by diagnostic assessment
treat_id = context.record_decision(
    category       = "treatment_modification",
    scenario       = "Metformin discontinuation required — eGFR 28 below contraindication threshold",
    reasoning      = "NICE NG28 and BNF both contraindicate metformin at eGFR < 30; switch to gliclazide MR 30mg OD",
    outcome        = "discontinue_metformin_initiate_gliclazide",
    confidence     = 0.97,
    decision_maker = "clinical_ai_v3",
)
graph.add_causal_relationship(diag_id, treat_id, "CAUSED")

# MDT audit report
chain = context.get_causal_chain(treat_id, direction="upstream", max_depth=3)
print("MDT Decision Audit — Treatment Modification")
print("=" * 50)
for d in chain:
    print("Caused by: [{}] {} (confidence={:.0%})".format(
        d.category, d.outcome, d.confidence
    ))

insights = graph.get_decision_insights()
cs = insights["confidence_stats"]
print("\nSession decisions: {}  |  mean confidence: {:.2f}".format(
    insights["total_decisions"], cs["mean"]
))
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A credit decisioning system records every loan decision against a versioned lending policy, links borderline approvals to stress-test decisions causally, and exports a complete decision audit trail for SR 11-7 model governance review.

```python
from semantica.context import AgentContext, ContextGraph, PolicyEngine, Policy
from semantica.context import Decision, DecisionRecorder
from semantica.vector_store import VectorStore
from datetime import datetime

graph   = ContextGraph()
engine  = PolicyEngine(graph_store=graph)
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=graph,
    decision_tracking=True,
)

engine.add_policy(Policy(
    policy_id   = "lending_policy_v3",
    name        = "Lending Compliance Policy v3",
    description = "Credit decisions require confidence >= 0.85 and documented reasoning",
    rules       = {"min_confidence": 0.85, "requires_reasoning": True},
    category    = "loan_approval",
    version     = "3.0",
    created_at  = datetime.now(),
    updated_at  = datetime.now(),
))

# Check precedents before approving
precedents = context.find_precedents(
    "first-time buyer mortgage borderline DSTI stressed rate scenario",
    limit=3,
)
for p in precedents:
    print("Prior: {} → {} ({:.0%})".format(p.scenario[:40], p.outcome, p.confidence))

# Stress-test decision precedes approval decision
stress_id = context.record_decision(
    category       = "stress_test",
    scenario       = "APP-2025-994421: LTV 78%, DSTI 38% at current rate; DSTI rises to 44% at +300bps",
    reasoning      = "DSTI 44% under stress exceeds 35% guideline threshold — requires LMI and income verification",
    outcome        = "stress_test_conditional_pass",
    confidence     = 0.88,
    decision_maker = "risk_model_v3",
)

# Approval decision influenced by stress test
d = Decision(
    decision_id    = "loan_dec_994421",
    category       = "loan_approval",
    scenario       = "APP-2025-994421: first-time buyer, LTV 78%, credit score 714, 30yr fixed",
    reasoning      = "Credit score 714 exceeds 700 minimum; LTV within 80% cap; conditional on LMI given stress-test DSTI",
    outcome        = "approved_conditional_lmi_required",
    confidence     = 0.89,
    timestamp      = datetime.now(),
    decision_maker = "credit_model_v3",
)

if engine.check_compliance(d, "lending_policy_v3"):
    loan_id = context.record_decision(
        category=d.category, scenario=d.scenario,
        reasoning=d.reasoning, outcome=d.outcome, confidence=d.confidence,
        decision_maker=d.decision_maker,
    )
    graph.add_causal_relationship(stress_id, loan_id, "INFLUENCED")
    engine.record_policy_application(d.decision_id, "lending_policy_v3", "3.0")
    print("Loan decision recorded — policy compliant.")

    # SR 11-7 explainability report
    explanation = context.trace_decision_explainability(loan_id)
    print("Upstream influences:", len(explanation.get("upstream_decisions", [])))
    print("Total connections  :", explanation["total_connections"])
```

</Tab>

</Tabs>

## Persisting Decisions Across Restarts

When using the local `ContextGraph`, save at the end of every session and load at the start of the next. All decision nodes, causal edges, and FAISS embeddings are restored.

```python
# End of session
context.save("agent_state/")
# Writes: agent_state/knowledge_graph.json + FAISS index

# Start of next session
context = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(),
    decision_tracking=True,
)
context.load("agent_state/")

# All past decisions are searchable immediately
results = context.find_precedents("APT29 infrastructure attribution", limit=5)
```

## Related Guides

- [Context Graphs](context-graphs) — how `ContextGraph` stores decision nodes and causal edges
- [Distance Intelligence](distance-intelligence) — `trace_decision_causality()` annotates causal chains with confidence decay and distance bands
- [Provenance](provenance) — W3C PROV-O audit trail that wraps decision records in standards-compliant provenance
- [MCP Server](mcp-server) — expose decision recording and precedent search to LLM agents via the `record_decision` and `find_precedents` tools
- [Change Management](change-management) — checkpoint decision state with `flush_checkpoint()` for versioned snapshots
