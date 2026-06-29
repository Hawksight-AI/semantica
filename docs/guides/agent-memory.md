---
title: "Agent Memory"
description: "How AgentContext stores, retrieves, and manages persistent agent memory — hierarchical short-term and long-term layers, FAISS-backed semantic retrieval, graph-enriched context, and cross-session persistence across defense, security, clinical, and financial deployments."
icon: "brain"
---

`AgentContext` maintains a persistent memory layer for LLM agents — storing observations as vector embeddings, retrieving them by semantic similarity, and optionally blending graph proximity into the ranking. Use it when your agent needs to recall past findings across sessions without re-reading source material on every restart.

## What Is Agent Memory?

Agent Memory provides persistent storage and intelligent retrieval of information across multiple agent sessions. `AgentContext` is the core component that orchestrates memory storage, retrieval, and management by combining three key systems:

**VectorStore** handles semantic search using vector embeddings. It stores text as high-dimensional vectors and retrieves similar content through cosine similarity or other distance metrics.

**ContextGraph** maintains structured knowledge as nodes (entities) and edges (relationships). This enables multi-hop traversal and graph-aware retrieval that follows connections between related entities.

**AgentContext** orchestrates both components, providing a unified interface for storing memories, retrieving relevant context, and managing conversations across sessions.

**Persistent memory vs stateless retrieval:** Traditional RAG systems lose context between sessions. Agent Memory persists learned information, conversation history, and accumulated knowledge across restarts, enabling long-term memory and cross-session recall.

## Why Use Agent Memory?

**Cross-session recall.** Agents remember previous interactions, findings, and decisions without re-processing source material after restarts.

**Long-term knowledge accumulation.** Information builds up over time as agents process more documents, creating increasingly rich knowledge bases for future queries.

**Conversation history.** Agents maintain context within conversations and can reference earlier parts of extended interactions or investigations.

**Graph-aware retrieval.** Beyond simple semantic similarity, retrieval follows entity relationships to find connected information that pure vector search would miss.

**Decision tracking.** Record decisions with full context and reasoning paths, enabling audit trails and precedent matching for similar future scenarios.

## When To Use / When Not To Use

**Use Agent Memory for:**
- Long-running agents that need to accumulate knowledge over time
- Research assistants that build understanding across multiple sessions
- Investigation workflows where context builds incrementally
- Systems that must remember prior interactions and decisions
- Scenarios requiring audit trails and decision precedents

**Do not use when:**
- Building simple stateless RAG systems for one-time document queries
- Performing one-off document searches without need for persistence
- Running temporary experiments that don't require knowledge retention
- Simple retrieval tasks where relationships between entities don't matter

<Info>
  This guide covers the memory layer. For graph-enriched traversal and entity linking, see [Context Graphs](context-graphs). For decision accountability — recording, auditing, and causally tracing what the agent chose — see [Decision Intelligence](decision-intelligence).
</Info>

## Setting Up a Persistent Memory Context

Configure the vector store, knowledge graph, and `AgentContext` together at startup so all three components persist to disk at the same path.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# The VectorStore relies on explicit save()/load() for persistence
ti_vs = VectorStore(
    backend="faiss",
    dimension=768,
)

# The ContextGraph holds entity nodes and their relationships
ti_graph = ContextGraph(advanced_analytics=True)

# AgentContext orchestrates everything
ti_agent = AgentContext(
    vector_store=ti_vs,
    knowledge_graph=ti_graph,
    retention_days=365,          # CTI reports stay relevant for a year
    max_memories=50000,          # ring buffer ceiling — oldest evicted first
    graph_expansion=True,        # enable multi-hop graph traversal in retrieve()
    max_expansion_hops=2,
    hybrid_alpha=0.5,            # 50% semantic score / 50% graph-structural score
    decision_tracking=True,      # enable record_decision() and find_precedents()
    kg_algorithms=True,          # Node2Vec embeddings, centrality, link prediction
)
```

The `hybrid_alpha` parameter controls how retrieval blends semantic similarity (pure vector search) with graph-structural similarity (topology of the knowledge graph). At `0.5` the agent treats both signals equally. For a freshly ingested corpus with a sparse graph, you might start closer to `0.0` and increase as the graph fills in.

## Storing What the Agent Learns

### Single observations

Every piece of intelligence the agent processes can be stored with a single call. The string is embedded and indexed immediately; the optional metadata travels with it and is available in every retrieval result.

```python
# Store a single finding from an OSINT feed
memory_id = ti_agent.store(
    "APT29 uses HAMMERTOSS for C2 communication over Twitter and GitHub",
    metadata={
        "source": "mandiant_apt29_report",
        "actor": "APT29",
        "technique": "T1102",   # Web Service
        "tlp": "WHITE",
    },
)
# memory_id is a UUID string — use it to retrieve or forget this item later

# Tag observations to an active incident so they can be retrieved as a group
ti_agent.store(
    "New C2 indicator: c2-upd4te[.]ru resolves to 185.220.101.47, cert hash a3f4b8c1...",
    metadata={"type": "ioc", "confidence": 0.92, "source": "internal_hunt"},
    conversation_id="incident_ir2025_0847",
    user_id="analyst_zhang",
)
```

The `conversation_id` acts as a namespace. Memories tagged with `incident_ir2025_0847` can be retrieved as a group later — useful for building a per-incident context window without polluting the global search index.

### Ingesting document corpora

When `store()` receives a list, it treats each element as a document, builds a graph of entities and relationships extracted from the text, and returns statistics about what was created.

```python
stats = ti_agent.store(
    [
        {
            "content": "APT29 infrastructure cluster: 185.220.101.0/24, AS200651",
            "metadata": {"source": "shadowserver", "actor": "APT29", "ioc_type": "network"},
        },
        {
            "content": "SolarWinds supply chain compromise attributed to APT29, 2020",
            "metadata": {"source": "us_cert_aa20-352a", "actor": "APT29", "campaign": "SUNBURST"},
        },
        {
            "content": "NOBELIUM (APT29) leverages OAuth token theft against cloud workloads",
            "metadata": {"source": "msft_blog_2023", "actor": "APT29", "technique": "T1528"},
        },
    ],
    extract_entities=True,       # extract actor, IP, CVE, technique nodes
    extract_relationships=True,  # link actor → campaign → technique → infrastructure
    link_entities=True,          # merge duplicate entity mentions across docs
)

print("Stored: {}, Graph nodes: {}, Graph edges: {}".format(
    stats["stored_count"],   # 3 — one per document
    stats["graph_nodes"],    # entities extracted and upserted into the graph
    stats["graph_edges"],    # relationships between those entities
))
```

After this call the knowledge graph contains nodes for APT29, HAMMERTOSS, the infrastructure subnet, the SUNBURST campaign, and OAuth token theft — all linked to each other. Those graph links are what enable multi-hop retrieval: ask about "cloud OAuth attacks" and the agent can follow the graph from the technique node back to APT29 and then forward to the infrastructure indicators.

## Retrieving Relevant Memory

### Semantic retrieval

The most direct retrieval call searches by semantic similarity — no keyword match required. The embedding of your query is compared against all stored memory embeddings, and the top matches are returned with scores.

```python
results = ti_agent.retrieve(
    "cloud OAuth token theft campaigns",
    max_results=8,
    min_score=0.2,
)

for r in results:
    actor = r.get("metadata", {}).get("actor", "unknown")
    print("[{:.3f}]  [{}]  {}".format(r["score"], actor, r["content"][:80]))

# [0.912]  [APT29]  NOBELIUM (APT29) leverages OAuth token theft against cloud workloads
# [0.741]  [APT29]  SolarWinds supply chain compromise attributed to APT29, 2020
# [0.683]  [APT29]  APT29 infrastructure cluster: 185.220.101.0/24, AS200651
```

The agent found the OAuth finding at the top — not because the query contained the exact phrase, but because the embedding space places "cloud OAuth token theft campaigns" close to "NOBELIUM leverages OAuth token theft against cloud workloads."

### Graph-anchored retrieval with proximity scoring

When you have a specific entity as the center of your investigation, anchor the retrieval to that node and blend semantic score with graph-proximity score.

```python
results = ti_agent.retrieve(
    "cloud OAuth token theft campaigns",
    max_results=10,
    use_graph=True,
    anchor_node="APT29",      # Breadth-First Search (BFS) starts from this node in the knowledge graph
    max_hops=3,
    proximity_weight=0.35,    # 65% semantic + 35% proximity — tune to your graph density
    min_score=0.1,
)

for r in results:
    # combined_score blends semantic score and graph proximity
    score = r.get("combined_score", r["score"])
    hop  = r.get("hop_distance", "-")
    band = r.get("distance_band", "-")  # "direct", "near", "mid-range", "distant"
    print("[{:.3f}]  hop={}  band={}  {}".format(score, hop, band, r["content"][:70]))
```

The `proximity_weight` parameter is a per-call override — you can use heavy proximity weighting when pivoting on a specific actor and drop back to pure semantic search when exploring broadly.

### Graph-grounded reasoning

When you need a natural-language answer that synthesizes multiple memory items, use `query_with_reasoning()` to retrieve context from the graph and ask the LLM to ground its answer in those sources.

```python
from semantica.llms import Groq

llm = Groq(model="llama-3.1-8b-instant", api_key="YOUR_GROQ_KEY")

result = ti_agent.query_with_reasoning(
    "Which threat actors are associated with SMB lateral movement in EMEA "
    "and what infrastructure do they share with cloud OAuth campaigns?",
    llm_provider=llm,
    max_results=15,
    max_hops=3,
)

print(result["response"])       # grounded natural-language answer
print(result["confidence"])     # aggregated retrieval confidence score

# Inspect the sources the answer is grounded in
for src in result["sources"]:
    print("  -", src["content"][:60])
```

The result includes a `reasoning_path` field that traces exactly which graph edges were traversed to reach the answer — useful for analyst review and audit.

## Building a Working Memory Window

Use the `conversation_id` filter to scope retrieval to the active session and combine incident-scoped history with global semantic search.

```python
incident_id = "ir2025_0847"

# Store each new alert as it arrives, tagged to the incident
ti_agent.store(
    "Alert: lateral movement detected from WKSTN-047 to DC01 via SMB (PsExec artifact)",
    metadata={"type": "alert", "severity": "critical", "technique": "T1021.002"},
    conversation_id=incident_id,
    user_id="analyst_zhang",
)

ti_agent.store(
    "Analyst note: WKSTN-047 user jsmith flagged for suspicious login from 10.2.5.40 at 03:14 UTC",
    metadata={"type": "analyst_note"},
    conversation_id=incident_id,
    user_id="analyst_zhang",
)

# Retrieve the full incident thread
incident_history = ti_agent.conversation(
    incident_id,
    max_items=50,
    reverse=False,          # chronological order
    include_metadata=True,
)

for item in incident_history:
    role = item["metadata"].get("type", "note")
    print("[{}] {}".format(role, item["content"][:80]))

# Combine incident-scoped history with a semantic search across global memory
context_items = ti_agent.retrieve(
    "SMB lateral movement PsExec domain controller",
    max_results=5,
    use_graph=True,
    conversation_id=incident_id,  # filter to this incident's memories only
)
```

This pattern lets the agent build a focused working memory window for each incident while the global vector index accumulates knowledge across all incidents over time.

## Domain Examples

<Tabs>
<Tab title="Defense — CTI/Threat">
A threat-intelligence fusion cell ingests OSINT feeds, MISP events, and internal hunt findings continuously. The agent must correlate new indicators against known actor profiles and produce attribution assessments grounded in accumulated intelligence — not just the latest report.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import Groq

ti_graph = ContextGraph(advanced_analytics=True, node_embeddings=True)
ti_agent = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ti_graph,
    retention_days=365,
    max_memories=50000,
    hybrid_alpha=0.6,
    decision_tracking=True,
)

# Ingest a fresh CTI report — entities and infrastructure flow into the graph
ti_agent.store(
    [
        {"content": "APT29 infrastructure cluster: 185.220.101.0/24, AS200651",
         "metadata": {"source": "shadowserver", "actor": "APT29", "tlp": "WHITE"}},
        {"content": "SolarWinds supply chain compromise attributed to APT29, campaign SUNBURST",
         "metadata": {"source": "us_cert_aa20-352a", "actor": "APT29", "campaign": "SUNBURST"}},
        {"content": "NOBELIUM (APT29) leverages OAuth token theft against cloud workloads",
         "metadata": {"source": "msft_blog_2023", "actor": "APT29", "technique": "T1528"}},
    ],
    extract_entities=True,
    extract_relationships=True,
)

# New hunt finding — is this C2 domain connected to APT29?
ti_agent.store(
    "New C2 indicator: c2-upd4te[.]ru resolves to 185.220.101.47, cert hash a3f4b8...",
    metadata={"type": "ioc", "confidence": 0.92, "source": "internal_hunt"},
    conversation_id="hunt_2025_q3",
)

# Graph-anchored attribution query: start from APT29, traverse 3 hops
llm = Groq(model="llama-3.1-8b-instant", api_key="YOUR_GROQ_KEY")
attribution = ti_agent.query_with_reasoning(
    "Is c2-upd4te[.]ru connected to APT29 based on infrastructure overlap?",
    llm_provider=llm,
    max_results=10,
    max_hops=3,
)
print(attribution["response"])
print("Confidence: {:.0%}".format(attribution["confidence"]))

# Persist intelligence base across analyst shifts
ti_agent.save("ti_state/")
```

</Tab>
<Tab title="Security — SOC/Incident">
A SOC analyst assistant carries context across shift handoffs. Tier 1 logs the initial alert and triage verdict; Tier 2 picks up with full incident history already loaded, without reading back through a ticket trail. The agent surfaces relevant runbook steps and finds similar past incidents for MTTR estimation.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore
from semantica.llms import Groq

soc_graph = ContextGraph()
soc_agent = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=soc_graph,
    retention_days=180,
    max_memories=100000,
    decision_tracking=True,
)

# Preload runbook knowledge base once — it persists across restarts
soc_agent.store([
    "T1021.002 (SMB/Windows Admin Shares): isolate host, reset service accounts, check for credential dumping",
    "T1003.001 (LSASS Memory): collect memory dump, run Mimikatz signatures, notify IR team",
    "T1190 (Exploit Public-Facing Application): check WAF logs, correlate with CVE feed, patch window 4h",
])

incident_id = "ir-2025-0847"

# Tier 1 logs the alert
soc_agent.store(
    "Alert: host WKSTN-047 failed 14 Kerberos AS-REQ in 30s from 10.2.5.40",
    metadata={"type": "alert", "severity": "high", "technique": "T1110.003"},
    conversation_id=incident_id,
    user_id="tier1_chen",
)
soc_agent.store(
    "Lateral movement confirmed: 10.2.5.40 connected to DC01 via PsExec",
    metadata={"type": "finding", "severity": "critical", "technique": "T1021.002"},
    conversation_id=incident_id,
    user_id="tier1_chen",
)

# Record the containment decision for audit and precedent matching
decision_id = soc_agent.record_decision(
    category="containment",
    scenario="Confirmed lateral movement from WKSTN-047 to DC01 via SMB",
    reasoning="PsExec artifact detected; immediate isolation prevents DC compromise",
    outcome="isolated_wkstn047",
    confidence=0.95,
    entities=["WKSTN-047", "DC01"],
    decision_maker="tier1_chen",
)

# Surface the matching runbook steps
runbook = soc_agent.retrieve(
    "SMB lateral movement with PsExec to domain controller",
    max_results=3,
    use_graph=True,
)
for step in runbook:
    print("[{:.3f}] {}".format(step["score"], step["content"]))

# Find similar past incidents — Tier 2 uses these to estimate resolution time
precedents = soc_agent.find_precedents(
    "lateral movement SMB domain controller compromise",
    category="containment",
    limit=3,
)
for p in precedents:
    print("Past: {} -> {} ({:.0%})".format(p.scenario[:50], p.outcome, p.confidence))

# Tier 2 loads the full incident context without reading the ticket
soc_agent.save("soc_state/")
```

</Tab>
<Tab title="Life Science — Clinical/Pharma">
A clinical decision support agent maintains patient context across consultations and carries treatment history forward. The agent surfaces guideline contraindications before a prescribing decision, then records the decision with full causal tracing for MDT audit.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

clinical_graph = ContextGraph(advanced_analytics=True)
clinical_agent = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=clinical_graph,
    retention_days=3650,      # 10-year clinical record retention
    max_memories=500000,
    decision_tracking=True,
)

# Load guidelines once — ADA, BNF, NICE — persists across sessions
clinical_agent.store([
    {"content": "ACE inhibitors are first-line for hypertension in diabetic patients (ADA 2024)",
     "metadata": {"source": "ADA_2024", "category": "guideline", "strength": "A"}},
    {"content": "Metformin contraindicated in eGFR < 30 mL/min/1.73m2 — risk of lactic acidosis",
     "metadata": {"source": "BNF_2024", "category": "contraindication", "strength": "absolute"}},
    {"content": "SGLT2 inhibitors reduce cardiovascular events in T2DM with CKD stage 3a (CREDENCE trial)",
     "metadata": {"source": "NEJM_CREDENCE", "category": "guideline", "strength": "A"}},
], extract_entities=True, extract_relationships=True)

patient_id = "PT-00841"

# Build patient context for this consultation
clinical_agent.store(
    "Patient PT-00841: T2DM, hypertension, eGFR 28 mL/min/1.73m2, no penicillin allergy",
    metadata={"type": "patient_summary", "patient_id": patient_id},
    conversation_id="consult_2025_07_01",
    user_id="dr_okonkwo",
)
clinical_agent.store(
    "Current medications: lisinopril 10mg, atorvastatin 40mg, aspirin 75mg",
    metadata={"type": "medication_list", "patient_id": patient_id},
    conversation_id="consult_2025_07_01",
)

# Before prescribing metformin — check the guideline base
contraindications = clinical_agent.retrieve(
    "metformin prescribing with reduced kidney function eGFR",
    max_results=5,
    use_graph=True,
    conversation_id="consult_2025_07_01",
)
for item in contraindications:
    category = item.get("metadata", {}).get("category", "?")
    print("[{:.3f}]  [{}]  {}".format(item["score"], category, item["content"][:80]))
# [0.947]  [contraindication]  Metformin contraindicated in eGFR < 30 mL/min/1.73m2 ...
# [0.821]  [guideline]         SGLT2 inhibitors reduce cardiovascular events in T2DM with CKD ...

# Record the decision — eGFR 28 falls below the absolute contraindication threshold
decision_id = clinical_agent.record_decision(
    category="treatment_modification",
    scenario="T2DM patient PT-00841 eGFR 28: metformin dose review required",
    reasoning=(
        "eGFR 28 falls below absolute contraindication threshold of 30 mL/min/1.73m2 "
        "per BNF_2024. Discontinue metformin; initiate dapagliflozin review per CREDENCE."
    ),
    outcome="discontinued_metformin_initiated_dapagliflozin_review",
    confidence=0.97,
    entities=["PT-00841", "metformin", "dapagliflozin", "eGFR"],
    decision_maker="dr_okonkwo",
)

# Explainability trace for MDT audit
explanation = clinical_agent.trace_decision_explainability(decision_id)
print("Guideline connections traced: {}".format(explanation.get("total_connections", 0)))

clinical_agent.save("clinical_state/{}/".format(patient_id))
```

</Tab>
<Tab title="Banking — Risk/Compliance">
A mortgage underwriting agent carries regulatory knowledge and application context through the decisioning workflow. Every credit decision is recorded with the exact regulatory guidance that grounded it, producing a defensible audit trail for model risk governance review.

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

credit_graph = ContextGraph(advanced_analytics=True)
credit_agent = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=credit_graph,
    retention_days=2555,      # 7-year regulatory retention
    max_memories=1000000,
    decision_tracking=True,
    kg_algorithms=True,
)

# Load regulatory knowledge base — Basel III, CRR, EBA guidelines
credit_agent.store([
    {"content": "Basel III: CET1 capital ratio minimum 4.5% + 2.5% conservation buffer",
     "metadata": {"source": "BCBS_Basel3", "category": "capital_requirement"}},
    {"content": "PD floor for retail exposures: 0.1% under IRB approach (CRR Art. 160)",
     "metadata": {"source": "CRR_Art160", "category": "risk_parameter"}},
    {"content": "DSTI ratio > 40% requires enhanced creditworthiness assessment per EBA GL 2020/06",
     "metadata": {"source": "EBA_GL_2020_06", "category": "affordability"}},
    {"content": "Adverse action notice required within 30 days of credit denial (ECOA Reg. B)",
     "metadata": {"source": "ECOA_RegB", "category": "regulatory_obligation"}},
], extract_entities=True, extract_relationships=True)

app_id = "APP-2025-994421"

# Load application context
credit_agent.store(
    "Applicant APP-2025-994421: gross income 82000 GBP, requested 320000 GBP 30yr mortgage, LTV 78%",
    metadata={"type": "application_summary", "app_id": app_id},
    conversation_id=app_id,
)
credit_agent.store(
    "Credit bureau: score 714, 0 defaults in 7yr, 2 hard inquiries last 12mo, DSTI 38%",
    metadata={"type": "bureau_data", "app_id": app_id},
    conversation_id=app_id,
)

# Retrieve regulatory guidance relevant to this application
guidance = credit_agent.retrieve(
    "mortgage affordability DSTI 38% regulatory requirements LTV 78%",
    max_results=5,
    use_graph=True,
    conversation_id=app_id,
)
for g in guidance:
    source = g.get("metadata", {}).get("source", "?")
    print("[{:.3f}]  [{}]  {}".format(g["score"], source, g["content"][:80]))
# [0.891]  [EBA_GL_2020_06]  DSTI ratio > 40% requires enhanced creditworthiness ...
# [0.724]  [CRR_Art160]      PD floor for retail exposures: 0.1% under IRB approach ...

# Record the decision — DSTI 38% is below the 40% EBA threshold
decision_id = credit_agent.record_decision(
    category="mortgage_origination",
    scenario="320k GBP 30yr mortgage, LTV 78%, DSTI 38%, credit score 714",
    reasoning=(
        "Score 714 exceeds 680 floor; DSTI 38% within EBA GL 2020/06 threshold of 40%; "
        "LTV 78% requires standard LMI; no derogatory history in 7yr; "
        "stress test at +300bps passes affordability."
    ),
    outcome="approved_conditional_lmi",
    confidence=0.89,
    entities=[app_id, "LTV_78pct", "DSTI_38pct"],
    decision_maker="underwriting_model_v4",
)

# Find similar precedents for model governance review
precedents = credit_agent.find_precedents(
    "mortgage approval borderline DSTI affordability stress test",
    category="mortgage_origination",
    limit=5,
)
for p in precedents:
    print("Precedent: {} -> {} ({:.0%})".format(p.scenario[:50], p.outcome, p.confidence))

credit_agent.save("credit_state/{}/".format(app_id))
```

</Tab>
</Tabs>

## Persisting and Restoring State

At the end of an analyst shift — or before a process restart — call `save()` to write the full context to disk. On next startup, call `load()` to restore it completely.

```python
# save() writes memory JSON plus backend-specific vector-store artifacts
# under agent_state/vector_store/ and the graph export at knowledge_graph.json.
# With the default VectorStore implementation this includes:
#   agent_state/agent_memory.json
#   agent_state/vector_store/store_data.pkl
#   agent_state/vector_store/index.bin
#   agent_state/knowledge_graph.json
ti_agent.save("agent_state/")
```

When a new process starts — or a new analyst logs in — restore from that checkpoint:

```python
from semantica.context import AgentContext, ContextGraph
from semantica.vector_store import VectorStore

# Create a fresh context with matching configuration
ti_agent_restored = AgentContext(
    vector_store=VectorStore(backend="faiss", dimension=768),
    knowledge_graph=ContextGraph(advanced_analytics=True),
    retention_days=365,
    decision_tracking=True,
)

# load() restores all three components from disk
ti_agent_restored.load("agent_state/")

# Every memory, graph edge, and decision precedent is now available
results = ti_agent_restored.retrieve("APT29 OAuth token theft cloud infrastructure")
```

<Info>
  `AgentMemory` itself is saved as JSON, but the vector store persists its own index and vector payload separately. `load()` restores those backend artifacts rather than re-embedding memories on demand, so keep the same vector-store backend, dimension, and scoring setup across sessions.
</Info>

## Taking Checkpoints During Analysis

For long-running analysis loops, take named snapshots before and after key steps so you can diff what the agent added during each phase.

```python
# Snapshot before the analysis loop starts
ti_agent.checkpoint("pre_enrichment")

# ... store new evidence, extract entities, record decisions ...

# Snapshot after enrichment completes
ti_agent.checkpoint("post_enrichment")

# See exactly what changed
diff = ti_agent.diff_checkpoints("pre_enrichment", "post_enrichment")
print("Decisions added:     {}".format(len(diff["decisions_added"])))
print("Relationships added: {}".format(len(diff["relationships_added"])))

# Optionally persist via TemporalVersionManager (requires temporal_version_manager= at init)
# ti_agent.flush_checkpoint("post_enrichment")
```

## Memory Lifecycle and Housekeeping

Retention is applied automatically on every `store()` call — items older than `retention_days` are pruned without any manual intervention. You can also remove specific memories or clear a full conversation namespace.

```python
# Forget a specific memory by ID
ti_agent.forget(memory_id="some-uuid-string")

# Clear all memories tagged to a specific incident
cleared = ti_agent.forget(conversation_id="incident_ir2025_0847")
print("Cleared {} items".format(cleared))

# Clear everything older than 90 days
old_cleared = ti_agent.clear(days_old=90)

# Get current memory statistics
s = ti_agent.stats()
print("Total memories: {}".format(s.get("total_items", 0)))
```

## Common Pitfalls

**Forgetting to persist memory before shutdown.** Agent Memory is stored in memory during execution. Without calling `save()` before process termination, all accumulated memories, graph relationships, and conversations are lost.

**Using the same conversation namespace for unrelated tasks.** Conversation IDs should scope related interactions. Using a single conversation for multiple unrelated investigations pollutes retrieval results and makes context less focused.

**Storing excessive low-value information.** Not every observation needs permanent storage. Focus on storing insights, decisions, and significant findings rather than verbose raw logs or temporary calculations.

**Using Agent Memory when simple retrieval would be sufficient.** For one-time document lookups or stateless queries, traditional retrieval is simpler and more efficient than setting up persistent memory infrastructure.

**Retrieving too much context and increasing latency.** Large `max_results`, high `max_hops`, or broad queries can retrieve excessive context, increasing LLM token usage and response latency. Start with focused retrieval parameters.

## Related Guides

- [Context Graphs](context-graphs) — How the underlying `ContextGraph` stores entity nodes and decision nodes; temporal interval reasoning; deduplication before node insertion; ontology from graph.
- [Decision Intelligence](decision-intelligence) — Recording decisions as graph nodes with causal chains and policy gating.
- [Multi-Agent Systems](multi-agent) — Coordinating multiple agents through a shared `AgentContext` and save/load handoffs.
- [LLM Integrations](llm-integrations) — Configuring the LLM provider passed to `query_with_reasoning()`.
- [Deduplication Guide](deduplication) — Full reference for `DuplicateDetector`, `EntityMerger`, similarity methods, and cluster strategies.
- [Ontology Management](ontology) — Generate and validate OWL ontologies from the knowledge graph; export to Turtle, OWL/XML, JSON-LD.
- [Context Module Reference](../reference/context) — Full API: `AgentContext`, `AgentMemory`, `MemoryItem`, `ContextRetriever`.
- [Vector Store Reference](../reference/vector_store) — FAISS, Qdrant, pgvector, Pinecone backends.
